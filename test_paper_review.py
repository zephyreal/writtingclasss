import json,time
from datetime import datetime
from contextlib import contextmanager
import pytest
from test_app import a,student,teacher,doc
from paper_queue import BJT,peak,next_daily,ReviewQueue
from review_pipeline import normalize_score

QUOTE='本文研究激光焊接速度与熔深的关系。'
ORIGINAL_SETTINGS=a.ai_settings

@pytest.fixture(autouse=True)
def isolated_queue(monkeypatch):
    with a.db() as c:
        c.execute('DELETE FROM throttle')
        c.execute("UPDATE submissions SET status='待批改' WHERE status IN ('AI排队中','AI定时待批改')")
        c.execute('DELETE FROM paper_review_jobs')
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'dummy','model':'test','base_url':'https://example.invalid/v1','auto_review':False,'auto_return':False})
    monkeypatch.setattr(a.REVIEW_QUEUE,'settings',lambda:a.ai_settings())
    monkeypatch.setattr(a.REVIEW_QUEUE,'wake',lambda:None)

def assignment(t):
    body={'title':'本次引言练习','instructions':'只写引言，交代问题和研究空白。','grading_instructions':'本次不评价实验结果，重点看研究空白。','rubric':[{'name':'研究问题', 'max':60},{'name':'论证表达','max':40}]}
    r=t.post('/api/assignments',json=body);assert r.status_code==200,r.text
    return r.json()['id'],body

def upload(s,aid):
    r=s.post('/api/submissions',data={'assignment_id':aid},files={'file':('draft.docx',doc())});assert r.status_code==200,r.text
    return next(x['submission']['id'] for x in s.get('/api/assignments').json() if x['id']==aid)

def test_edit_assignment_auth_rubric_revision_and_preservation():
    t=teacher();s=student('editassign100');aid,body=assignment(t);sid=upload(s,aid)
    assert s.put(f'/api/assignments/{aid}',json=body).status_code==403
    t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':88,'feedback':'已评稿件','published':True})
    changed={**body,'title':'修改后的引言练习','expected_revision':1}
    assert t.put(f'/api/assignments/{aid}',json=changed).json()['revision']==2
    row=next(x for x in s.get('/api/assignments').json() if x['id']==aid)
    assert row['title']==changed['title'] and row['submission']['score']==88
    assert t.put(f'/api/assignments/{aid}',json=changed).status_code==409
    changed.pop('expected_revision');changed['rubric']=[{'name':'不完整','max':50}]
    assert t.put(f'/api/assignments/{aid}',json=changed).status_code==400
    changed['rubric']=[{'name':'重复','max':50},{'name':'重复','max':50}]
    assert t.put(f'/api/assignments/{aid}',json=changed).status_code==400

def test_scoring_is_sum_of_valid_grounded_dimensions():
    rubric=[{'name':'问题','max':60},{'name':'表达','max':40}]
    document={'text':QUOTE,'complete':True}
    rows=[{'name':'问题','score':51,'comment':'研究问题较为明确，仍需具体化','quote':QUOTE},{'name':'表达','score':32.5,'comment':'表达基本清楚，仍需完善衔接','quote':QUOTE}]
    result=normalize_score(rows,rubric,document,{'readable':True})
    assert result['score']==83.5 and all(x['quote_verified'] for x in result['dimensions'])
    for bad in (True,61,float('nan'),float('inf'),-1):
        rows[0]['score']=bad
        assert normalize_score(rows,rubric,document,{'readable':True})['score'] is None
    rows[0]['score']=51;rows[0]['quote']='编造的引用不存在'
    assert normalize_score(rows,rubric,document,{'readable':True})['score'] is None
    assert normalize_score([],rubric,document,{'readable':False})['score'] is None

def test_real_review_uses_teacher_requirements_but_does_not_publish(monkeypatch):
    t=teacher();s=student('scoring100');aid,body=assignment(t);sid=upload(s,aid);seen={}
    @contextmanager
    def prepared(path):yield {'text':QUOTE,'complete':True,'page_count':1,'warnings':[],'pages':[{'page_no':1,'text':QUOTE,'image_path':'test.jpg'}]}
    def ai(system,payload):
        seen.update(payload)
        return {'formal_check':{'decision':'pass','confidence':.95,'readable':True,'issues':[]},'dimensions':[{'name':r['name'],'score':r['max']*.8,'comment':'有明确原文依据，仍可进一步完善','quote':QUOTE} for r in payload['rubric']],'score':999,'summary':'建议反馈'}
    monkeypatch.setattr(a,'prepare_document',prepared);monkeypatch.setattr(a,'ai_call',ai)
    assert a.run_review(sid)
    row=next(x for x in t.get('/api/teacher/submissions').json() if x['id']==sid)
    assert row['ai']['score']==80 and row['score'] is None and not row['published']
    assert seen['grading_instructions']==body['grading_instructions'] and row['ai']['scoring_basis']['revision']==1
    body['instructions']='修改后的要求：需增加文献对比。'
    assert t.put(f'/api/assignments/{aid}',json=body).status_code==200
    row=next(x for x in t.get('/api/teacher/submissions').json() if x['id']==sid)
    assert row['assignment_revision']==2 and row['ai']['scoring_basis']['revision']==1

def test_batch_schedule_idempotency_cancel_and_permissions():
    t=teacher();s=student('schedule100');aid,body=assignment(t);sid=upload(s,aid)
    future=datetime.fromtimestamp(time.time()+3600,BJT).replace(tzinfo=None).isoformat(timespec='minutes')
    assert s.post('/api/teacher/reviews/batch',json={'assignment_id':aid}).status_code==403
    assert t.post('/api/teacher/reviews/batch',json={'assignment_id':aid,'run_at':'2020-01-01T00:00'}).status_code==400
    r=t.post('/api/teacher/reviews/batch',json={'assignment_id':aid,'run_at':future}).json();assert r['queued']==1
    r=t.post('/api/teacher/reviews/batch',json={'assignment_id':aid,'run_at':future}).json();assert r['queued']==0 and r['skipped']==1
    assert not a.REVIEW_QUEUE.run_one()
    jobs=t.get('/api/teacher/review-jobs').json()['jobs'];jid=jobs[0]['id']
    assert s.delete(f'/api/teacher/review-jobs/{jid}').status_code==403
    assert s.delete(f'/api/submissions/{sid}').status_code==409
    assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':90,'feedback':'','published':True}).status_code==409
    assert t.delete(f'/api/teacher/review-jobs/{jid}').status_code==200
    assert s.delete(f'/api/submissions/{sid}').status_code==200

def test_queue_runs_once_skips_reviewed_and_blocks_edits(monkeypatch):
    t=teacher();s=student('batch100');other=student('batch200');aid,body=assignment(t)
    sid=upload(s,aid);otherid=upload(other,aid)
    with a.db() as c:c.execute('UPDATE submissions SET ai_json=? WHERE id=?',('{}',otherid))
    r=t.post('/api/teacher/reviews/batch',json={'assignment_id':aid}).json()
    assert r['queued']==1 and r['skipped']==1
    assert t.put(f'/api/assignments/{aid}',json=body).status_code==409
    seen=[]
    def run(id):
        seen.append(id)
        with a.db() as c:c.execute("UPDATE submissions SET ai_json='{}',status='形式预审通过，待教师评阅' WHERE id=?",(id,))
        return True
    monkeypatch.setattr(a,'run_review',run)
    assert a.REVIEW_QUEUE.run_one() and not a.REVIEW_QUEUE.run_one() and seen==[sid]
    assert t.put(f'/api/assignments/{aid}',json=body).status_code==200
    assert t.get('/api/teacher/review-jobs').json()['counts']['completed']==1

def test_persistent_queue_recovery_does_not_retry_running(monkeypatch):
    t=teacher();s=student('recover100');aid,_=assignment(t);sid=upload(s,aid)
    jid=a.REVIEW_QUEUE.enqueue(sid,run_at=time.time()+3600,wake=False)
    q=ReviewQueue(a.db,a.POOL,lambda sid:True,lambda:a.ai_settings())
    with a.db() as c:assert c.execute('SELECT state FROM paper_review_jobs WHERE id=?',(jid,)).fetchone()[0]=='pending'
    with a.db() as c:
        c.execute("UPDATE paper_review_jobs SET state='running' WHERE id=?",(jid,))
        c.execute("UPDATE submissions SET status='AI批改中' WHERE id=?",(sid,))
    q=ReviewQueue(a.db,a.POOL,lambda sid:pytest.fail('must not rebill'),lambda:a.ai_settings())
    assert not q.run_one(time.time()+7200)
    with a.db() as c:assert c.execute('SELECT state FROM paper_review_jobs WHERE id=?',(jid,)).fetchone()[0]=='failed'

def test_bjt_schedule_and_peak_gate(monkeypatch):
    def stamp(value):return datetime.fromisoformat(value).replace(tzinfo=BJT).timestamp()
    assert peak(stamp('2026-10-19T09:00'))
    assert not peak(stamp('2026-10-19T12:00'))
    assert peak(stamp('2026-10-19T14:00'))
    assert not peak(stamp('2026-10-19T18:00'))
    assert not peak(stamp('2026-10-18T10:00'))
    assert next_daily('00:30',stamp('2026-10-19T16:00'))==stamp('2026-10-20T00:30')
    t=teacher();s=student('peak100');aid,_=assignment(t);sid=upload(s,aid)
    a.REVIEW_QUEUE.enqueue(sid,run_at=0,wake=False)
    monkeypatch.setattr(a.REVIEW_QUEUE,'settings',lambda:{'key':'x','model':'x','off_peak_only':True})
    seen=[];monkeypatch.setattr(a,'run_review',lambda sid:seen.append(sid) or True)
    assert not a.REVIEW_QUEUE.run_one(stamp('2026-10-19T09:01')) and not seen
    assert a.REVIEW_QUEUE.run_one(stamp('2026-10-19T18:01')) and seen==[sid]

def test_scheduled_auto_submission_and_settings_validation(monkeypatch):
    monkeypatch.setattr(a,'ai_settings',ORIGINAL_SETTINGS)
    t=teacher();body={'base_url':'https://example.invalid/v1','model':'test','key':'dummy','review_mode':'scheduled','review_time':'00:30','off_peak_only':True}
    assert t.post('/api/teacher/ai-settings',json={**body,'review_time':'25:80'}).status_code==422
    assert t.post('/api/teacher/ai-settings',json=body).status_code==200
    saved=t.get('/api/teacher/ai-settings').json()
    assert saved['review_mode']=='scheduled' and saved['auto_review'] and saved['off_peak_only'] and 'key' not in saved
    s=student('autotime100');aid,_=assignment(t);sid=upload(s,aid)
    with a.db() as c:
        job=c.execute('SELECT * FROM paper_review_jobs WHERE submission_id=?',(sid,)).fetchone()
        assert time.time()<job['run_at']<time.time()+86401
        assert c.execute('SELECT status FROM submissions WHERE id=?',(sid,)).fetchone()[0]=='AI定时待批改'

def test_render_crossing_peak_defers_without_paid_request(monkeypatch):
    t=teacher();s=student('defer100');aid,_=assignment(t);sid=upload(s,aid)
    a.REVIEW_QUEUE.enqueue(sid,wake=False)
    monkeypatch.setattr(a.REVIEW_QUEUE,'settings',lambda:{'key':'x','model':'x','off_peak_only':False})
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'x','model':'x','base_url':'https://example.invalid','off_peak_only':True})
    monkeypatch.setattr(a,'peak',lambda stamp:True)
    @contextmanager
    def prepared(path):yield {'text':QUOTE}
    monkeypatch.setattr(a,'prepare_document',prepared)
    monkeypatch.setattr(a,'ai_call',lambda *args:pytest.fail('must not make paid request'))
    assert not a.REVIEW_QUEUE.run_one()
    with a.db() as c:assert c.execute('SELECT state FROM paper_review_jobs WHERE submission_id=?',(sid,)).fetchone()[0]=='pending'

def test_server_lifespan_starts_and_stops_queue(monkeypatch):
    from fastapi.testclient import TestClient
    events=[]
    monkeypatch.setattr(a.REVIEW_QUEUE,'start',lambda:events.append('start'))
    monkeypatch.setattr(a.REVIEW_QUEUE,'stop',lambda:events.append('stop'))
    with TestClient(a.app) as c:assert c.get('/healthz').json()=={'ok':True}
    assert events==['start','stop']
