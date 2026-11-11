import hashlib
import io
import json
import zipfile
from pathlib import Path
import pytest
from test_app import a,doc
from test_writing_workflow import setup,upload,detail,TEXT
import writing_studio as studio


def reviewed(t,s,aid,n=1):
    assert upload(s,aid,n).status_code==200
    d=detail(s,aid);sid=d['submission_id'];assert a.run_review(sid)
    return sid,detail(s,aid)['rounds'][-1]['id']


def clear_uncertain(t,rid):
    assert t.post(f'/api/teacher/writing/rounds/{rid}/issue-review',json={'issue_id':f'r{round_no(rid)}-i2','decision':'dismissed','reason':'原文不存在该处证据，驳回意见'}).status_code==200


def round_no(rid):
    with a.db() as c:return c.execute('SELECT round_no FROM writing_rounds WHERE id=?',(rid,)).fetchone()[0]


def plan(t,aid,action,ids=None):
    r=t.post(f'/api/teacher/writing/assignments/{aid}/batch-preview',json={'action':action,'student_ids':ids or []})
    assert r.status_code==200,r.text
    return r.json()


def apply(t,aid,p,ids=None):
    return t.post(f'/api/teacher/writing/assignments/{aid}/batch-apply',json={'action':p['action'],'student_ids':ids or [],'token':p['token']})


def test_stage_defaults_validation_and_submission_snapshot(setup):
    t,s,other,aid,calls=setup
    original=next(x for x in t.get('/api/assignments').json() if x['id']==aid)
    assert original['stage_rubrics']==[]  # Existing explicit rubric is preserved.
    result=t.post('/api/assignments',json={'title':'新阶段写作','workflow':True})
    assert result.status_code==200
    new=result.json()['id'];assignment=next(x for x in t.get('/api/assignments').json() if x['id']==new)
    assert assignment['stage_rubrics']==studio.DEFAULT_RUBRICS
    assert all(sum(d['max'] for d in rr)==100 for rr in assignment['stage_rubrics'])
    assert t.put(f'/api/assignments/{new}',json={'title':'新阶段写作','workflow':True,'stage_rubrics':[[{'name':'不完整','max':100}]]}).status_code==400
    assert upload(s,new,1).status_code==200
    sid=detail(s,new)['submission_id']
    assert a.run_review(sid)
    assert calls[-1]['assignment']['rubric']==studio.DEFAULT_RUBRICS[0]
    with a.db() as c:
        snapshot=json.loads(c.execute('SELECT assignment_snapshot FROM writing_rounds WHERE submission_id=?',(sid,)).fetchone()[0])
        assert snapshot['round_no']==1 and snapshot['rubric']==studio.DEFAULT_RUBRICS[0]
    assert s.post('/api/assignments',json={'title':'越权修改','workflow':True}).status_code==403


def test_reader_text_grounding_and_private_images(setup,tmp_path):
    t,s,other,aid,calls=setup
    assert upload(s,aid,1).status_code==200
    d=detail(s,aid);rid=d['rounds'][0]['id'];sid=d['submission_id']
    base=f'/api/writing/rounds/{rid}'
    before=s.get(base+'/source');assert before.status_code==200
    assert before.json()['text_only'] and before.json()['pages'][0]['text']
    assert other.get(base+'/source').status_code==404
    assert a.run_review(sid)
    view=s.get(base+'/source').json();anchors=view['anchors']
    assert len(anchors)==1 and anchors[0]['issue_id']=='r1-i1'
    located=anchors[0];text=view['pages'][0]['text']
    assert text[located['start']:located['end']]=='适用范围有待更多试验检验'
    assert view['review']['score'] is None and '_image' not in json.dumps(view)
    with a.db() as c:
        source=json.loads(c.execute('SELECT source_json FROM writing_rounds WHERE id=?',(rid,)).fetchone()[0]);source['pages'][0]['_image']=str(tmp_path/'outside.jpg')
        c.execute('UPDATE writing_rounds SET source_json=? WHERE id=?',(json.dumps(source),rid))
    (tmp_path/'outside.jpg').write_bytes(b'private')
    assert t.get(base+'/pages/1').status_code==404
    assert other.get(base+'/pages/1').status_code==404
    image=tmp_path/'render.jpg';image.write_bytes(b'jpeg-placeholder')
    with a.db() as c:path=c.execute('SELECT path FROM writing_rounds WHERE id=?',(rid,)).fetchone()[0]
    studio.cache_source(rid,path,{'complete':True,'text':TEXT,'pages':[{'page_no':1,'text':TEXT,'image_path':str(image)}]})
    assert t.get(base+'/pages/1').content==b'jpeg-placeholder'
    assert s.get(base+'/pages/1').status_code==200
    assert other.get(base+'/pages/1').status_code==404
    studio.cache_source(rid,path,{'complete':True,'text':TEXT+'\n'+TEXT,'pages':[{'page_no':1,'text':TEXT},{'page_no':2,'text':TEXT}]})
    assert s.get(base+'/source').json()['anchors']==[]  # Repeated quotes are ambiguous, never guessed.


def test_batch_preview_commit_and_publication_are_separate(setup):
    t,s,other,aid,calls=setup
    assert t.put(f'/api/assignments/{aid}',json={'title':'科研写作','workflow':True,'round_weights':[25]*4}).status_code==200
    uid=s.get('/api/me').json()['id'];ids=[uid];rids=[]
    for n in range(1,5):
        sid,rid=reviewed(t,s,aid,n);rids.append(rid)
        p=plan(t,aid,'draft',ids)
        assert not any(i['round_id']==rid for i in p['items'])
        assert any('核验' in i['reason'] for i in p['skipped'])
        clear_uncertain(t,rid)
    p=plan(t,aid,'draft',ids);assert len(p['items'])==4
    assert apply(t,aid,p,ids).status_code==200
    assert apply(t,aid,p,ids).status_code==409  # Stale/repeated confirmations cannot mutate again.
    assert all(r['teacher_score'] is None for r in detail(s,aid)['rounds'])
    private=t.get(f'/api/teacher/writing/submissions/{sid}').json()
    assert all(r['teacher_score']==85 for r in private['rounds'])
    assert t.post(f'/api/teacher/writing/rounds/{rids[0]}/grade',json={'score':50,'published':False}).status_code==200
    assert not plan(t,aid,'draft',ids)['items']  # Never overwrite a teacher's score.
    p=plan(t,aid,'publish_rounds',ids)
    assert t.post(f'/api/teacher/writing/rounds/{rids[1]}/grade',json={'score':80,'published':False}).status_code==200
    assert apply(t,aid,p,ids).status_code==409
    p=plan(t,aid,'publish_rounds',ids);assert len(p['items'])==4
    assert apply(t,aid,p,ids).status_code==200
    assert detail(s,aid)['rounds'][0]['teacher_score']==50
    assert detail(s,aid)['score'] is None and detail(s,aid)['grading']['total'] is None
    p=plan(t,aid,'publish_totals',ids);assert p['items'][0]['score']==75
    assert apply(t,aid,p,ids).status_code==200
    assert detail(s,aid)['score']==75
    assert len(calls)==4  # Batch grading never calls a paid model.
    assert not plan(t,aid,'draft',ids)['items']
    assert s.post(f'/api/teacher/writing/assignments/{aid}/batch-preview',json={'action':'draft'}).status_code==403
    assert s.post(f'/api/teacher/writing/assignments/{aid}/batch-apply',json={'action':'publish_totals','token':p['token']}).status_code==403
    with a.db() as c:assert c.execute("SELECT COUNT(*) FROM audit WHERE action LIKE 'writing-batch-%'").fetchone()[0]>=3


def test_stale_rubric_and_busy_rows_are_not_bulk_adopted(setup):
    t,s,other,aid,calls=setup;sid,rid=reviewed(t,s,aid);clear_uncertain(t,rid)
    assert t.put(f'/api/assignments/{aid}',json={'title':'新要求','workflow':True}).status_code==200
    uid=s.get('/api/me').json()['id'];p=plan(t,aid,'draft',[uid])
    assert not p['items'] and any('旧版' in x['reason'] for x in p['skipped'])
    assert t.post(f'/api/teacher/writing/rounds/{rid}/grade',json={'score':90,'published':False}).status_code==200
    with a.db() as c:c.execute("UPDATE submissions SET status='AI批改中' WHERE id=?",(sid,))
    assert not plan(t,aid,'publish_rounds',[uid])['items']
    assert t.post(f'/api/teacher/writing/assignments/{aid}/batch-preview',json={'action':'draft','student_ids':[999999]}).status_code==400


def test_cohort_includes_missing_students_and_ppt_state(setup):
    t,s,other,aid,calls=setup;sid,rid=reviewed(t,s,aid)
    uid=s.get('/api/me').json()['id'];other_id=other.get('/api/me').json()['id']
    assert t.put(f'/api/teacher/students/{uid}/presentation/writing',json={'presented':True,'date':'2026-11-11','topic':'AI辅助科研'}).status_code==200
    data=t.get(f'/api/teacher/writing/assignments/{aid}/cohort').json();rows={r['id']:r for r in data['students']}
    assert len(rows[uid]['rounds'])==1 and rows[uid]['needs_review']==1 and rows[uid]['ppt_presented']==1
    assert rows[other_id]['rounds']==[] and rows[other_id]['submission_id'] is None
    assert s.get(f'/api/teacher/writing/assignments/{aid}/cohort').status_code==403
    assert t.request('DELETE',f'/api/teacher/students/{other_id}',json={'student_no':'workflow02','reason':'重复账号测试'}).status_code==200
    assert other_id not in {r['id'] for r in t.get(f'/api/teacher/writing/assignments/{aid}/cohort').json()['students']}


def test_portfolio_originals_private_grades_and_escaped_report(setup):
    t,s,other,aid,calls=setup;sid,rid=reviewed(t,s,aid)
    uid=s.get('/api/me').json()['id']
    assert t.post(f'/api/teacher/writing/rounds/{rid}/grade',json={'score':0,'feedback':'<script>private teacher draft</script>','published':False}).status_code==200
    with a.db() as c:
        r=json.loads(c.execute('SELECT review_json FROM writing_rounds WHERE id=?',(rid,)).fetchone()[0]);r['summary']='<script>unsafe content</script>';c.execute('UPDATE writing_rounds SET review_json=? WHERE id=?',(json.dumps(r),rid))
    endpoint=f'/api/writing/assignments/{aid}/portfolio'
    assert other.get(endpoint+f'?user_id={uid}').status_code==403
    assert other.get(endpoint).status_code==404
    response=s.get(endpoint);assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        record=json.loads(z.read('learning-record.json'));report=z.read('打开学习档案.html').decode()
        assert record['rounds'][0]['teacher_score'] is None and record['rounds'][0]['review']['score'] is None
        assert 'private teacher draft' not in report and '<script>' not in report and '&lt;script&gt;' in report
        assert hashlib.sha256(z.read('round-1/original.docx')).hexdigest()==record['files'][0]['sha256']
        assert z.read('round-1/original.docx')==s.get(f'/api/writing/rounds/{rid}/file').content
        assert 'path' not in record['rounds'][0] and 'phone' not in record['student']
    teacher_response=t.get(endpoint+f'?user_id={uid}')
    with zipfile.ZipFile(io.BytesIO(teacher_response.content)) as z:
        record=json.loads(z.read('learning-record.json'));assert record['rounds'][0]['teacher_score']==0
        report=z.read('打开学习档案.html').decode();assert '教师分数：0' in report and '&lt;script&gt;private teacher draft' in report


def test_weight_and_deadline_changes_do_not_invalidate_same_scoring_policy(setup):
    t,s,other,aid,calls=setup;sid,rid=reviewed(t,s,aid);clear_uncertain(t,rid)
    uid=s.get('/api/me').json()['id']
    assert len(plan(t,aid,'draft',[uid])['items'])==1
    assignment=next(a for a in t.get('/api/assignments').json() if a['id']==aid)
    assert t.put(f'/api/assignments/{aid}',json={'title':assignment['title'],'instructions':assignment['instructions'],'workflow':True,'rubric':assignment['rubric'],'round_weights':[25,25,25,25],'deadline':'2099-01-01T00:00'}).status_code==200
    p=plan(t,aid,'draft',[uid]);assert len(p['items'])==1
    assert apply(t,aid,p,[uid]).status_code==200
    assignment=next(a for a in t.get('/api/assignments').json() if a['id']==aid)
    assert t.put(f'/api/assignments/{aid}',json={'title':assignment['title'],'instructions':assignment['instructions'],'workflow':True,'rubric':assignment['rubric'],'round_weights':[10,20,30,40],'deadline':'2099-01-02T00:00'}).status_code==200
    assert len(plan(t,aid,'publish_rounds',[uid])['items'])==1
