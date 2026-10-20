import io
import json
import zipfile
from contextlib import contextmanager
from xml.etree import ElementTree as ET
import pytest
from test_app import a,student,teacher,doc
import writing_workflow as w
ORIGINAL_AI_CALL=a.ai_call

TEXT='本文研究激光焊接速度与熔深的关系。采用三组实验测试不同速度对熔深的影响，以截面金相结果作为评价依据。结果表明在本实验条件下熔深存在差异，适用范围有待更多试验检验。'

@pytest.fixture
def setup(tmp_path,monkeypatch):
    import sqlite3
    with sqlite3.connect(a.DB) as source,sqlite3.connect(tmp_path/'course.db') as target:source.backup(target)
    monkeypatch.setattr(a,'DB',tmp_path/'course.db');a.init()
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'','model':'test','auto_review':False})
    t=teacher();s=student('workflow01');other=student('workflow02')
    response=t.post('/api/assignments',json={'title':'科研写作','workflow':True,'rubric':[{'name':'论证','max':70},{'name':'修改','max':30}]})
    assert response.status_code==200,response.text
    aid=response.json()['id']
    @contextmanager
    def prepared(path):yield {'text':TEXT,'pages':[],'page_count':1,'complete':True,'warnings':[]}
    monkeypatch.setattr(a,'prepare_document',prepared)
    calls=[]
    def ai(prompt,payload):
        calls.append(payload)
        n=payload['round_no']
        return {'summary':'本轮说明了研究对象，需要进一步限定结论范围。','strengths':['明确了研究对象'],
          'issues':[{'category':'论证结构','problem':'结论范围需要说明','quote':'适用范围有待更多试验检验','criterion':'论证','suggestion':'说明实验范围','question':'哪些条件保持一致？','uncertain':False},
                    {'category':'事实规范','problem':'虚构引文不得变成必改项','quote':'文档中并不存在这句话','criterion':'论证','uncertain':False}],
          'tracking':[{'issue_id':f'r{i}-i1','status':'improved','quote':'适用范围有待更多试验检验','reason':'补充了范围'} for i in range(1,n)],
          'next_actions':['回应关键问题'],
          'practice':{'a':'虚构教学片段A','b':'虚构教学片段B','question':'哪一段更清楚？','analysis':'参考分析，并非唯一正确判断。'},
          'dimensions':[{'name':'论证','score':60,'comment':'论证尚需限定','quote':'本文研究激光焊接速度与熔深的关系'}, {'name':'修改','score':25,'comment':'能说明边界','quote':'适用范围有待更多试验检验'}],
          'method_card':{'improved':['结论中补充了范围说明'],'watch':['继续核对研究边界']}}
    monkeypatch.setattr(a,'ai_call',ai)
    return t,s,other,aid,calls

def upload(s,aid,n,**kwargs):
    return s.post(f'/api/writing/assignments/{aid}/submit',data={'round_no':n,**kwargs},files={'file':('draft.docx',doc())})

def detail(s,aid):return s.get(f'/api/writing/assignments/{aid}').json()

def test_four_rounds_scores_privacy_and_history(setup):
    t,s,other,aid,calls=setup
    assert detail(s,aid)['can_submit']
    assert upload(s,aid,2).status_code==409
    for n in range(1,5):
        assert upload(s,aid,n).status_code==200
        d=detail(s,aid);sid=d['submission_id'];rid=d['rounds'][-1]['id']
        assert upload(s,aid,n+1).status_code in (400,409)
        assert other.get(f'/api/writing/rounds/{rid}/file').status_code==404
        assert s.get(f'/api/writing/rounds/{rid}/file').status_code==200
        assert a.run_review(sid)
        d=detail(s,aid);r=d['rounds'][-1]
        assert r['review']['score'] is None and r['review']['dimensions']==[]
        assert r['review']['issues'][1]['needs_review']
        assert 'analysis' not in r['review']['practice']
        practice=s.post(f'/api/writing/rounds/{rid}/practice',json={'answer':'片段A更清楚，因为说明了条件。'})
        assert practice.status_code==200 and 'analysis' in practice.json()
        assert s.post(f'/api/writing/rounds/{rid}/retry').status_code==409
        if n<4:
            assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':80,'feedback':'','published':True}).status_code==409
            assert calls[-1]['previous_reviews'] or n==1
    assert len(calls)==4
    assert a.run_review(sid) and len(calls)==4  # repeated teacher request never rebills a completed round
    assert not detail(s,aid)['can_submit']
    assert upload(s,aid,4).status_code==409
    teacher_data=t.get(f'/api/teacher/writing/submissions/{sid}').json()
    assert teacher_data['rounds'][-1]['review']['score']==85
    assert len(teacher_data['rounds'])==4
    assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':87,'feedback':'教师复核','published':True}).status_code==200
    assert detail(s,aid)['score']==87
    assert detail(s,aid)['rounds'][-1]['review']['score']==85
    assert s.post(f'/api/writing/assignments/{aid}/method',json={'reminders':['核对证据','说明范围','比较文献']}).status_code==200
    assert detail(s,aid)['method']
    assert other.get(f'/api/teacher/writing/submissions/{sid}').status_code==403

def test_failed_check_replace_and_rule_snapshot(setup,monkeypatch):
    t,s,other,aid,calls=setup
    assert upload(s,aid,1).status_code==200
    d=detail(s,aid);sid=d['submission_id'];rid=d['rounds'][0]['id']
    first=t.get(f'/api/teacher/writing/submissions/{sid}').json()['rounds'][0]['filename']
    assert first=='draft.docx'
    assert upload(s,aid,1,replace='true').status_code==200
    def fail(*args):raise ValueError('模拟接口故障')
    monkeypatch.setattr(a,'ai_call',fail)
    assert not a.run_review(sid)
    assert detail(s,aid)['can_replace'] and not detail(s,aid)['can_submit']
    assert upload(s,aid,2).status_code==409
    # Teacher editing requirements must not rewrite the snapshot of a submitted round.
    assert t.put(f'/api/assignments/{aid}',json={'title':'新题目','instructions':'新标准','workflow':True}).status_code==200
    with a.db() as c:
        snapshot=json.loads(c.execute('SELECT assignment_snapshot FROM writing_rounds WHERE id=?',(rid,)).fetchone()[0])
        assert snapshot['title']=='科研写作'
    assert t.put(f'/api/assignments/{aid}',json={'title':'新题目','instructions':'新标准','workflow':False}).status_code==409
    assert s.post('/api/submissions',data={'assignment_id':aid},files={'file':('a.docx',doc())}).status_code==409

def test_briefing_consent_review_and_editable_export(setup):
    t,s,other,aid,calls=setup
    assert upload(s,aid,1,shared='true').status_code==200
    d=detail(s,aid);sid=d['submission_id'];assert a.run_review(sid)
    base=f'/api/teacher/writing/{aid}/brief/1'
    report=t.get(base).json()
    assert report['reviewed']==1 and report['topics'][0]['students']==1
    assert len(report['candidates'])==1
    assert t.get(base+'/pptx').status_code==409
    draft=report['draft'];case=report['candidates'][0]
    draft['slides'].append({'title':'匿名案例','body':case['quote'],'round_id':case['round_id']})
    assert t.put(base,json=draft).status_code==200
    response=t.get(base+'/pptx');assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert 'ppt/slides/slide1.xml' in z.namelist()
        for name in z.namelist():
            if name.endswith(('.xml','.rels')):ET.fromstring(z.read(name))
        assert b'a:t' in z.read('ppt/slides/slide2.xml')
    assert other.get(base).status_code==403
    assert s.post(f'/api/writing/assignments/{aid}/withdraw-sharing').status_code==200
    assert not t.get(base).json()['candidates']
    assert t.get(base+'/pptx').status_code==409
    assert t.put(base,json=draft).status_code==409

def test_uncertain_tracking_and_no_early_score(setup):
    t,s,other,aid,calls=setup
    result=w.normalize({'summary':'有待核验','dimensions':[{'name':'论证','score':70}], 'tracking':[{'issue_id':'r1-i1','status':'improved','quote':'不存在','reason':'改好了'}]},TEXT,[{'name':'论证','max':100}],2,[{'issues':[{'id':'r1-i1'},{'id':'r1-i2'}]}])
    assert result['score'] is None and result['dimensions']==[]
    assert len(result['tracking'])==2 and all(t['status']=='uncertain' for t in result['tracking'])

def test_responses_surveys_and_manual_fallback(setup):
    t,s,other,aid,calls=setup
    base=f'/api/writing/assignments/{aid}'
    assert s.post(base+'/survey',json={'moment':'before','answers':[2,3,2]}).status_code==200
    assert s.post(base+'/survey',json={'moment':'after','answers':[4,4,4]}).status_code==409
    assert upload(s,aid,1).status_code==200
    d=detail(s,aid);sid=d['submission_id'];rid=d['rounds'][0]['id'];assert a.run_review(sid)
    response={'issue_id':'r1-i1','decision':'adapt','reason':'需要增加适用条件'}
    assert other.post(f'/api/writing/rounds/{rid}/response',json=response).status_code==404
    assert s.post(f'/api/writing/rounds/{rid}/response',json=response).status_code==200
    assert detail(s,aid)['rounds'][0]['responses'][0]['decision']=='adapt'
    assert upload(s,aid,2).status_code==200
    assert a.run_review(sid) and calls[-1]['student_decisions'][0]['decision']=='adapt'
    assert upload(s,aid,3).status_code==200
    endpoint=f'/api/teacher/writing/submissions/{sid}/manual-feedback'
    assert other.post(endpoint,json={'feedback':'请明确研究边界，补充修改说明后进入终稿。'}).status_code==403
    assert t.post(endpoint,json={'feedback':'请明确研究边界，补充修改说明后进入终稿。'}).status_code==200
    assert detail(s,aid)['can_submit']
    assert upload(s,aid,4).status_code==200 and a.run_review(sid)
    assert s.post(base+'/survey',json={'moment':'after','answers':[4,4,4]}).status_code==200
    brief=t.get(f'/api/teacher/writing/{aid}/brief/4').json()
    assert brief['survey']['paired_students']==1
    assert brief['survey']['before']==2.33 and brief['survey']['after']==4
    draft=brief['draft'];draft['published']=True
    endpoint=f'/api/teacher/writing/{aid}/brief/4'
    assert t.put(endpoint,json=draft).status_code==200
    assert detail(other,aid)['briefings'][0]['round_no']==4
    assert all('round_id' not in slide for slide in detail(other,aid)['briefings'][0]['slides'])

def test_teacher_delete_restore_keeps_versions_and_cancels_queue(setup,monkeypatch):
    t,s,other,aid,calls=setup
    assert s.delete(f'/api/assignments/{aid}').status_code==403
    assert upload(s,aid,1).status_code==200
    d=detail(s,aid);sid=d['submission_id'];rid=d['rounds'][0]['id']
    jid=a.REVIEW_QUEUE.enqueue(sid,wake=False)
    assert t.delete(f'/api/assignments/{aid}').json()['cancelled_jobs']==1
    assert not any(x['id']==aid for x in s.get('/api/assignments').json())
    assert not any(x['id']==sid for x in t.get('/api/teacher/submissions').json())
    assert s.get(f'/api/writing/assignments/{aid}').status_code==404
    assert upload(s,aid,1,replace='true').status_code==404
    assert t.post(f'/api/teacher/submissions/{sid}/ai').status_code==400 # API not configured
    with pytest.raises(a.HTTPException):a.REVIEW_QUEUE.enqueue(sid,wake=False)
    with a.db() as c:
        assert c.execute('SELECT state FROM paper_review_jobs WHERE id=?',(jid,)).fetchone()[0]=='cancelled'
        assert c.execute('SELECT 1 FROM writing_rounds WHERE id=?',(rid,)).fetchone()
    assert t.get('/api/teacher/assignments/deleted').json()[0]['id']==aid
    assert t.post(f'/api/teacher/assignments/{aid}/restore').status_code==200
    assert len(detail(s,aid)['rounds'])==1
    with a.db() as c:c.execute("UPDATE submissions SET status='AI批改中' WHERE id=?",(sid,))
    assert t.delete(f'/api/assignments/{aid}').status_code==409
    with a.db() as c:c.execute("UPDATE submissions SET status='待批改' WHERE id=?",(sid,))
    assert t.delete(f'/api/assignments/{aid}').status_code==200
    assert t.delete(f'/api/assignments/{aid}').status_code==404

def test_delete_published_legacy_grade_excluded_and_restored(setup):
    t,s,other,_,calls=setup
    aid=t.post('/api/assignments',json={'title':'普通作业','instructions':'写作练习'}).json()['id']
    assert s.post('/api/submissions',data={'assignment_id':aid},files={'file':('paper.docx',doc())}).status_code==200
    sid=next(x['submission']['id'] for x in s.get('/api/assignments').json() if x['id']==aid)
    assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':88,'feedback':'原评语','published':True}).status_code==200
    assert t.delete(f'/api/assignments/{aid}').status_code==200
    with a.db() as c:
        assert c.execute('SELECT score FROM submissions WHERE id=?',(sid,)).fetchone()[0]==88
    uid=s.get('/api/me').json()['id']
    assert next(x for x in t.get('/api/teacher/students').json() if x['id']==uid)['assignment_score'] is None
    assert s.post('/api/submissions',data={'assignment_id':aid},files={'file':('paper.docx',doc())}).status_code==404
    assert t.post(f'/api/teacher/assignments/{aid}/restore').status_code==200
    assert next(x for x in t.get('/api/teacher/students').json() if x['id']==uid)['assignment_score']==88

def test_invitation_required_capacity_and_revocation(setup):
    t,s,other,aid,calls=setup
    from test_app import client
    anon=client();body={'name':'新学生','student_no':'invite-new01','password':'test-password-123'}
    assert anon.post('/api/register',json=body).status_code==403
    assert s.post('/api/teacher/invites',json={}).status_code==403
    invitation=t.post('/api/teacher/invites',json={'label':'一人邀请码','max_uses':1,'valid_days':1}).json()
    assert 'code' in invitation
    assert 'code_hash' not in str(t.get('/api/teacher/access').json())
    assert anon.post('/api/register',json={**body,'invite_code':invitation['code']}).status_code==200
    assert anon.post('/api/register',json={**body,'student_no':'invite-new02','invite_code':invitation['code']}).status_code==403
    second=t.post('/api/teacher/invites',json={'max_uses':10}).json()
    assert t.delete('/api/teacher/invites/'+str(second['id'])).status_code==200
    assert anon.post('/api/register',json={**body,'student_no':'invite-new03','invite_code':second['code']}).status_code==403
    assert anon.post('/api/login',json={'student_no':body['student_no'],'password':body['password']}).status_code==200

def test_atomic_daily_user_and_site_limits(setup):
    t,s,other,aid,calls=setup
    from concurrent.futures import ThreadPoolExecutor
    uid=s.get('/api/me').json()['id'];uid2=other.get('/api/me').json()['id']
    assert t.post('/api/teacher/access',json={'student_daily_limit':2,'site_daily_limit':3}).status_code==200
    stamp=1900000000
    def reserve(_):
        try:a.reserve_ai_call(uid,stamp);return True
        except a.DailyQuotaExceeded:return False
    with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(reserve,range(10)))
    assert sum(results)==2
    a.reserve_ai_call(uid2,stamp)
    with pytest.raises(a.DailyQuotaExceeded):a.reserve_ai_call(uid2,stamp)
    a.reserve_ai_call(uid,stamp+86400) # new BJT day

def test_quota_returns_429_to_student_api(setup,monkeypatch):
    t,s,other,aid,calls=setup
    assert t.post('/api/teacher/access',json={'student_daily_limit':0,'site_daily_limit':20}).status_code==200
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'mock','model':'mock','base_url':'https://example.invalid'})
    monkeypatch.setattr(a,'ai_call',ORIGINAL_AI_CALL)
    response=s.post('/api/practice/ai?chapter_id=1')
    assert response.status_code==429 and int(response.headers['Retry-After'])>0

def test_paid_cache_and_failed_attempts_count_toward_quota(setup,monkeypatch):
    t,s,other,aid,calls=setup
    uid=s.get('/api/me').json()['id']
    assert t.post('/api/teacher/access',json={'student_daily_limit':2,'site_daily_limit':20}).status_code==200
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'mock-key','model':'mock','base_url':'https://example.invalid'})
    original_call=ORIGINAL_AI_CALL
    original_client=a.httpx.Client;sent=[]
    def handler(request):
        sent.append(1)
        if len(sent)==2:raise a.httpx.ConnectError('network failure')
        return a.httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})
    monkeypatch.setattr(a.httpx,'Client',lambda **kw:original_client(transport=a.httpx.MockTransport(handler)))
    payload={'nonce':'one','_usage_context':{'user_id':uid,'purpose':'quota-test'}}
    assert original_call('test',payload)=={'ok':True}
    assert original_call('test',payload)=={'ok':True} and len(sent)==1
    with pytest.raises(a.httpx.ConnectError):original_call('test',{**payload,'nonce':'two'})
    with pytest.raises(a.DailyQuotaExceeded):original_call('test',{**payload,'nonce':'three'})
    assert len(sent)==2

def test_quota_exhaustion_defers_paper_job(setup):
    t,s,other,aid,calls=setup
    assert upload(s,aid,1).status_code==200
    sid=detail(s,aid)['submission_id']
    from paper_queue import ReviewQueue
    def quota(sid):raise a.DailyQuotaExceeded('今日额度已用完',3000)
    q=ReviewQueue(a.db,a.POOL,quota,lambda:{'key':'mock','model':'mock'})
    jid=q.enqueue(sid,run_at=1000,wake=False)
    assert q.run_one(stamp=1001)
    with a.db() as c:
        job=c.execute('SELECT * FROM paper_review_jobs WHERE id=?',(jid,)).fetchone()
        assert job['state']=='pending' and job['run_at']==3000
    assert not q.run_one(stamp=2000)

def test_teacher_confirm_dismiss_preserves_ai_and_audit(setup):
    t,s,other,aid,calls=setup
    assert upload(s,aid,1,shared='true').status_code==200
    d=detail(s,aid);sid=d['submission_id'];rid=d['rounds'][0]['id'];assert a.run_review(sid)
    endpoint=f'/api/teacher/writing/rounds/{rid}/issue-review'
    body={'issue_id':'r1-i2','decision':'confirmed','reason':'教师已对照原稿核验，需要调整这条意见。'}
    assert other.post(endpoint,json=body).status_code==403
    assert any(x['issue']['id']=='r1-i2' for x in t.get('/api/teacher/writing/issues').json()['issues'])
    assert t.post(endpoint,json=body).status_code==200
    issue=detail(s,aid)['rounds'][0]['review']['issues'][1]
    assert not issue['needs_review'] and issue['teacher_review']['decision']=='confirmed'
    body.update(decision='dismissed',reason='再次核对，原建议不适用于本次任务。')
    assert t.post(endpoint,json=body).status_code==200
    assert detail(s,aid)['rounds'][0]['review']['issues'][1]['dismissed']
    with a.db() as c:
        raw=json.loads(c.execute('SELECT review_json FROM writing_rounds WHERE id=?',(rid,)).fetchone()[0])
        assert raw['issues'][1]['needs_review'] is True
        assert c.execute("SELECT COUNT(*) FROM audit WHERE target=? AND action LIKE 'writing-issue-%'",(f'{rid}/r1-i2',)).fetchone()[0]==2
        events=c.execute('SELECT * FROM writing_issue_review_events WHERE round_id=? AND issue_id=? ORDER BY id',(rid,'r1-i2')).fetchall()
        assert len(events)==2 and events[0]['decision']=='confirmed' and events[1]['decision']=='dismissed'

def test_fourth_round_score_keeps_warning_and_partial_sum(setup):
    t,s,other,aid,calls=setup
    rubric=[{'name':'论证','max':70},{'name':'修改','max':30}]
    raw={'summary':'反馈','dimensions':[{'name':'论证','score':60,'comment':'理由','quote':'引用无法匹配'},{'name':'修改','score':20,'comment':'理由','quote':TEXT[:10]}]}
    result=w.normalize(raw,TEXT,rubric,4,[])
    assert result['score']==80 and '引用未匹配' in result['score_warning']
    raw['dimensions'].pop()
    result=w.normalize(raw,TEXT,rubric,4,[])
    assert result['score'] is None and result['partial_score']==60 and result['partial_max']==70
    assert len(result['dimensions'])==1

def test_safe_errors_and_damaged_password(setup,monkeypatch):
    t,s,other,aid,calls=setup
    assert not a.pwdcheck('x','damaged') and not a.pwdcheck('x',None)
    assert upload(s,aid,1).status_code==200
    sid=detail(s,aid)['submission_id']
    def fail(*args):raise ValueError('/opt/private/file.docx secret internal detail')
    monkeypatch.setattr(a,'ai_call',fail)
    assert not a.run_review(sid)
    assert '/opt/private' not in detail(s,aid)['status']
