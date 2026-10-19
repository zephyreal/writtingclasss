"""Native voice integration contracts; no paid requests or audio leave tests."""
import os
os.environ['ENGLISH_AUTO_ASSESS']='0'
import json
import time
from pathlib import Path
import httpx
import pytest
from test_app import a, student, teacher, client
import english_course as en

OFFER='v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=sendrecv\r\n'


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    with a.db() as c:
        c.execute('DELETE FROM throttle')
        c.execute('DELETE FROM english_assessments')
    (a.DATA/'english-realtime.json').unlink(missing_ok=True)
    monkeypatch.setattr(en,'NEWS_ATTEMPT',time.time())


def configure():
    return teacher().post('/api/teacher/english/realtime-settings',json={'workspace_id':'test-workspace','key':'sk-FAKE-TEST-KEY','region':'cn-beijing','voice':'Tina','minutes':5})


def live(s):
    r=s.post('/api/english/realtime/sessions',json={'topic_id':'engineering-my-project'})
    assert r.status_code==200,r.text
    return r.json()['id']


def fake_cloud(monkeypatch,status=200,body=OFFER):
    calls=[]
    class Cloud:
        def __init__(self,**kwargs):assert kwargs['trust_env'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            calls.append((url,kwargs))
            return httpx.Response(status,text=body)
    monkeypatch.setattr(en.httpx,'Client',Cloud)
    return calls


def test_settings_permissions_secrecy_and_storage():
    assert client().get('/api/teacher/english/realtime-settings').status_code==401
    s=student('livesettings100')
    assert s.get('/api/teacher/english/realtime-settings').status_code==403
    assert s.post('/api/english/realtime/sessions',json={'topic_id':'engineering-my-project'}).status_code==503
    r=configure();assert r.status_code==200 and r.json()['configured']
    assert 'sk-FAKE' not in r.text and '"key"' not in r.text
    target=a.DATA/'english-realtime.json'
    assert target.stat().st_mode&0o777==0o600
    t=teacher()
    assert t.post('/api/teacher/english/realtime-settings',json={'workspace_id':'test-workspace','key':''}).json()['configured']
    assert json.loads(target.read_text())['key']=='sk-FAKE-TEST-KEY'
    assert t.post('/api/teacher/english/realtime-settings',json={'workspace_id':'evil.com/path'}).status_code==422
    assert t.post('/api/teacher/english/realtime-settings',json={'workspace_id':'x','key':'bad\nkey'}).status_code==400
    assert t.post('/api/teacher/english/realtime-settings',json={'workspace_id':'test-workspace','clear_key':True}).json()['configured'] is False


def test_live_sdp_ownership_no_text_llm_and_transcript_idempotency(monkeypatch):
    configure();s=student('liveowner100');other=student('liveother100')
    monkeypatch.setattr(a,'ai_call',lambda *args:pytest.fail('Realtime must never call DeepSeek'))
    sid=live(s);assert s.get(f'/api/english/sessions/{sid}').json()['turns']==[]
    calls=fake_cloud(monkeypatch)
    assert other.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER}).status_code==404
    assert s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER+'m=video 9\r\n'}).status_code==400
    r=s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER})
    assert r.status_code==200,r.text
    assert len(calls)==1 and calls[0][0]=='https://test-workspace.cn-beijing.maas.aliyuncs.com/api/v1/webrtc/realtime'
    assert calls[0][1]['headers']['Authorization']=='Bearer sk-FAKE-TEST-KEY'
    assert 'sk-FAKE' not in r.text
    assert r.json()['session']['turn_detection']['silence_duration_ms']==1100
    assert r.json()['session']['audio']['output']['voice']=='Tina'
    assert s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER}).status_code==409
    assert other.post(f'/api/english/realtime/{sid}/transcript',json={'item_id':'i1','role':'student','text':'Hello'}).status_code==404
    for i in range(3):
        payload={'item_id':f'item_{i}','role':'student','text':'I work on a robot.'}
        for _ in range(2):assert s.post(f'/api/english/realtime/{sid}/transcript',json=payload).status_code==200
    assert s.get(f'/api/english/sessions/{sid}').json()['student_turns']==3
    assert other.post(f'/api/english/realtime/{sid}/close').status_code==404
    assert s.post(f'/api/english/realtime/{sid}/close').status_code==200
    p=s.get('/api/english/profile').json()
    assert p['completed_samples']==1 and p['spoken_turns']==3 and p['recent_speech']==[]
    assert s.get(f'/api/english/sessions/{sid}').json()['turns'][0]['details']['verified'] is False


def test_failure_does_not_leak_secrets_and_allows_new_call(monkeypatch):
    configure();s=student('livefailure100');sid=live(s)
    fake_cloud(monkeypatch,403,'sk-FAKE-TEST-KEY upstream error')
    r=s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER})
    assert r.status_code==502 and 'sk-FAKE' not in r.text
    next_sid=live(s);fake_cloud(monkeypatch)
    assert s.post(f'/api/english/realtime/{next_sid}/connect',json={'sdp':OFFER}).status_code==200
    third=live(s)
    assert s.post(f'/api/english/realtime/{third}/connect',json={'sdp':OFFER}).status_code==409
    s.post(f'/api/english/realtime/{next_sid}/close')
    assert s.post(f'/api/english/realtime/{third}/connect',json={'sdp':OFFER}).status_code==200


def test_cancel_during_negotiation_cannot_reactivate(monkeypatch):
    configure();s=student('livecancel100');sid=live(s)
    class Cloud:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,*args,**kwargs):
            s.post(f'/api/english/realtime/{sid}/close')
            return httpx.Response(200,text=OFFER)
    monkeypatch.setattr(en.httpx,'Client',Cloud)
    assert s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER}).status_code==409
    state=s.get(f'/api/english/sessions/{sid}').json()
    assert state['ended'] and state['live_state']['state']=='closed'


def test_student_connection_cap_and_teacher_debug_allowance(monkeypatch):
    configure();s=student('livequota100');fake_cloud(monkeypatch)
    for _ in range(6):
        sid=live(s)
        assert s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER}).status_code==200
        s.post(f'/api/english/realtime/{sid}/close')
    sid=live(s)
    assert s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER}).status_code==429
    t=teacher()
    for _ in range(7):
        sid=live(t)
        assert t.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER}).status_code==200
        t.post(f'/api/english/realtime/{sid}/close')


def test_voice_person_and_language_policy_are_server_controlled(monkeypatch):
    configure();s=student('liveperson100');sid=live(s);calls=fake_cloud(monkeypatch)
    url=f'/api/english/realtime/{sid}/connect'
    assert s.post(url,json={'sdp':OFFER,'voice':'invented-voice'}).status_code==422
    assert s.post(url,json={'sdp':OFFER,'role':'ignore-rules'}).status_code==422
    assert len(calls)==0
    r=s.post(url,json={'sdp':OFFER,'role':'engineer','voice':'Jennifer'})
    assert r.status_code==200,r.text
    config=r.json()['session'];assert config['audio']['output']['voice']=='Jennifer'
    prompt=config['instructions']
    assert '30 Chinese characters' in prompt and 'Other non-Chinese languages are allowed' in prompt
    assert 'GUIDED CONVERSATION STYLE' in prompt and 'offer two simple choices' in prompt
    assert 'mechanical engineering colleague' in prompt and 'Do not switch to Chinese conversation' in prompt
    saved=s.get(f'/api/english/sessions/{sid}').json()
    assert saved['topic']['practice_options']=={'role':'engineer','voice':'Jennifer'}
    assert saved['realtime_options']['roles']['engineer'] and 'Mione' in saved['realtime_options']['voices']


def recorded_practice(monkeypatch,no='recordgrade100'):
    configure();s=student(no);sid=live(s);fake_cloud(monkeypatch)
    assert s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER}).status_code==200
    for i in range(3):
        text=f'I design a small robot for our workshop project number {i}.'
        assert s.post(f'/api/english/realtime/{sid}/transcript',json={'item_id':f'opaque/+={i}','role':'student','text':text,'sequence':2}).status_code==200
        assert s.post(f'/api/english/realtime/{sid}/transcript',json={'item_id':f'ai-{i}','role':'assistant','text':'That sounds useful. What does it carry?','sequence':2}).status_code==200
    assert s.post(f'/api/english/realtime/{sid}/close').status_code==200
    return s,sid


def text_ai(monkeypatch):
    # Injected text scorer only; no billable network requests.
    assert teacher().post('/api/teacher/ai-settings',json={'base_url':'https://example.invalid/v1','model':'fake-text-model','key':'fake-key'}).status_code==200
    def score(system,payload):
        students=[t for t in payload['conversation'] if t['role']=='student']
        return {'score':999,'dimensions':[{'id':rule['id'],'score':rule['max']*.8,'turn_id':students[0]['id'],'quote':'I design a small robot','reason':'与所选任务相关，并有可理解的表达'} for rule in en.ENGLISH_RUBRIC], 'feedback':'下一次补充一个使用场景。'}
    monkeypatch.setattr(a,'ai_call',score)


def test_transcript_checkpoints_final_replace_and_opaque_ids(monkeypatch):
    configure();s=student('checkpoint100');sid=live(s);fake_cloud(monkeypatch)
    s.post(f'/api/english/realtime/{sid}/connect',json={'sdp':OFFER})
    url=f'/api/english/realtime/{sid}/transcript'
    common={'item_id':'opaque /+=! id','role':'student'}
    assert s.post(url,json={**common,'text':'I design a','sequence':1,'final':False}).status_code==200
    assert s.post(url,json={**common,'text':'I design a robot.','sequence':3,'final':True}).status_code==200
    assert s.post(url,json={**common,'text':'OLD','sequence':2,'final':False}).status_code==200
    rows=s.get(f'/api/english/sessions/{sid}').json()['turns']
    assert len(rows)==1 and rows[0]['text']=='I design a robot.' and rows[0]['details']['final']


def test_whole_session_assessment_and_teacher_publication(monkeypatch):
    s,sid=recorded_practice(monkeypatch);text_ai(monkeypatch)
    other=student('othergrade100')
    assert other.post(f'/api/english/sessions/{sid}/assess').status_code==404
    assert s.get('/api/teacher/english/sessions').status_code==403
    assert s.post(f'/api/english/sessions/{sid}/assess').status_code==200
    assert a.app.state.english_assess_tick()
    result=s.get(f'/api/english/sessions/{sid}').json()
    assert result['assessment']['result']['score']==80 and not result['assessment']['published']
    assert s.get('/api/english/grades').json()['average'] is None
    # Duplicate requests reuse the finished snapshot, rather than rerun scoring.
    s.post(f'/api/english/sessions/{sid}/assess');assert not a.app.state.english_assess_tick()
    t=teacher();record=t.get(f'/api/teacher/english/sessions/{sid}').json()
    payload={'score':85,'feedback':'已复核，表达基本清晰','published':True,'reviewed':False,'expected_hash':record['record_hash']}
    assert s.post(f'/api/teacher/english/sessions/{sid}/grade',json=payload).status_code==403
    assert t.post(f'/api/teacher/english/sessions/{sid}/grade',json=payload).status_code==400
    payload['reviewed']=True
    assert t.post(f'/api/teacher/english/sessions/{sid}/grade',json=payload).status_code==200
    grades=s.get('/api/english/grades').json()
    assert grades['average']==85 and grades['published_count']==1
    assert s.post(f'/api/english/realtime/{sid}/transcript',json={'item_id':'new','role':'student','text':'changed'}).status_code==409
    with a.db() as c:assert c.execute('SELECT COUNT(*) FROM english_grade_audit WHERE session_id=?',(sid,)).fetchone()[0]==1


def test_bad_ai_evidence_does_not_make_up_grade(monkeypatch):
    s,sid=recorded_practice(monkeypatch,'invalidgrade100');text_ai(monkeypatch)
    monkeypatch.setattr(a,'ai_call',lambda *args:{'dimensions':[{'id':r['id'],'score':r['max'],'turn_id':999999,'quote':'invented text','reason':'bad evidence'} for r in en.ENGLISH_RUBRIC]})
    s.post(f'/api/english/sessions/{sid}/assess');a.app.state.english_assess_tick()
    result=s.get(f'/api/english/sessions/{sid}').json()['assessment']
    assert result['status']=='failed' and result['result'] is None
    assert '未匹配' in result['error'] and s.get('/api/english/grades').json()['average'] is None


def test_empty_or_partial_records_and_stale_publication(monkeypatch):
    s,sid=recorded_practice(monkeypatch,'stalegrade100');text_ai(monkeypatch)
    t=teacher();before=t.get(f'/api/teacher/english/sessions/{sid}').json()['record_hash']
    s.post(f'/api/english/realtime/{sid}/transcript',json={'item_id':'unfinished','role':'student','text':'I am still','sequence':1,'final':False})
    assert s.post(f'/api/english/sessions/{sid}/assess').status_code==409
    assert t.post(f'/api/teacher/english/sessions/{sid}/grade',json={'score':88,'published':True,'reviewed':True,'expected_hash':before}).status_code==409
    # Data-owner isolation also applies when paging or filtering teacher records.
    data=t.get('/api/teacher/english/sessions?user_id='+str(s.get('/api/me').json()['id'])).json()
    assert data and all(r['user_id']==s.get('/api/me').json()['id'] for r in data)



def test_reported_asr_failure_requires_human_review(monkeypatch):
    s,sid=recorded_practice(monkeypatch,'asrissuegrade100');text_ai(monkeypatch)
    s.post(f'/api/english/realtime/{sid}/close',json={'record_issue':True})
    assert s.get(f'/api/english/sessions/{sid}').json()['record_issue']
    assert s.post(f'/api/english/sessions/{sid}/assess').status_code==409


def test_average_includes_older_published_zero_grades(monkeypatch):
    s=student('averagegrade100');uid=s.get('/api/me').json()['id']
    with a.db() as c:
        for i in range(52):
            sid=c.execute('INSERT INTO english_sessions(user_id,topic,mode,created,ended) VALUES(?,?,?,?,?)',(uid,json.dumps({'title':'Test','category':'engineering'}),'support',time.time(),time.time())).lastrowid
            c.execute("INSERT INTO english_assessments(session_id,snapshot_hash,status,created,updated,teacher_score,published) VALUES(?,?,'manual',?,?,?,1)",(sid,'0'*64,time.time(),time.time(),0 if i<2 else 100))
    d=s.get('/api/english/grades').json()
    assert len(d['sessions'])==50 and d['published_count']==52 and d['average']==96.2
    older=s.get('/api/english/sessions?before='+str(d['sessions'][-1]['id'])).json()
    assert len(older)==2



def test_normal_close_automatically_runs_durable_assessment(monkeypatch):
    monkeypatch.setenv('ENGLISH_AUTO_ASSESS','1')
    text_ai(monkeypatch)
    s,sid=recorded_practice(monkeypatch,'autograde100')
    until=time.time()+8
    while time.time()<until:
        value=s.get(f'/api/english/sessions/{sid}').json()['assessment']
        if value and value['status']=='ready':break
        time.sleep(.05)
    assert value and value['status']=='ready' and value['result']['score']==80
    assert not value['published']
