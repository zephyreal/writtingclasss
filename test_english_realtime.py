"""Native voice integration contracts; no paid requests or audio leave tests."""
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
    with a.db() as c:c.execute('DELETE FROM throttle')
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
