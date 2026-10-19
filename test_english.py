import json
import time
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import pytest
from test_app import a, student, teacher, client
import english_course as en
import english_speech as speech
from vendor.speaklab.fluency import analyse


@pytest.fixture(autouse=True)
def english_clean_throttle(monkeypatch):
    with a.db() as c:c.execute('DELETE FROM throttle')
    # Tests never make paid requests even when older tests configured a dummy key.
    monkeypatch.setattr(en, 'NEWS_ATTEMPT', time.time())
    monkeypatch.setattr(a, 'ai_call', lambda *args: {'reply':'That sounds interesting. Why do you like it?', 'hint':'试试 I like it because…', 'corrections':[]})


def start(s):
    r=s.post('/api/english/sessions',json={'topic_id':'engineering-my-project'})
    assert r.status_code==200,r.text
    return r.json()


def answer(s,session,i,text='I work on a robot and I enjoy making useful machines.'):
    return s.post('/api/english/sessions/'+str(session['id'])+'/turn',json={'text':text,'expected_turns':i,'request_id':f'request-{session["id"]}-{i}'})


def test_fluency_arithmetic_and_missing_data():
    words=[{'w':'Um','start_ms':200,'end_ms':400},{'w':'hello','start_ms':900,'end_ms':1200}]
    m=analyse(words)
    assert m.word_count==2 and m.filler_count==1
    assert m.speech_rate_wpm==120 and m.articulation_rate==240
    assert m.pause_ratio==.5 and m.mean_length_run==1
    assert m.response_latency_ms==200
    assert analyse(None).speech_rate_wpm is None
    assert analyse([{'w':'hello'}]).pause_ratio is None


def test_english_auth_and_topic_validation():
    assert client().get('/api/english/topics').status_code==401
    s=student('enauth100')
    d=s.get('/api/english/topics').json()
    assert len([t for t in d['topics'] if t['kind']=='scenario'])==12
    assert not any('persona' in t for t in d['topics'])
    assert s.post('/api/english/news/refresh').status_code==403
    assert s.get('/api/teacher/english/students').status_code==403
    assert s.post('/api/english/profile',json={'interests':['unknown']}).status_code==400
    assert s.post('/api/english/sessions',json={'topic_id':'https://evil.example'}).status_code==404
    assert s.post('/api/english/profile',json={'interests':['engineering']}).status_code==200
    assert s.get('/api/english/topics').json()['topics'][0]['category']=='engineering'


def test_conversation_ownership_idempotency_and_text_not_audio():
    s=student('enowner100');other=student('enowner200');d=start(s);sid=d['id']
    assert d['turns'][0]['role']=='assistant'
    assert other.get(f'/api/english/sessions/{sid}').status_code==404
    assert other.post(f'/api/english/sessions/{sid}/end').status_code==404
    assert s.post(f'/api/english/sessions/{sid}/hint').json()['hint']
    r=answer(s,d,0);assert r.status_code==200,r.text
    r=answer(s,d,0);assert r.status_code==200 and r.json()['student_turns']==1
    turns=r.json()['turns'];assert turns[1]['details']['speech'] is None
    assert s.get('/api/english/profile').json()['spoken_turns']==0
    stale={'text':'Another answer','expected_turns':0,'request_id':'different-request'}
    assert s.post(f'/api/english/sessions/{sid}/turn',json=stale).status_code==409
    assert s.post(f'/api/english/sessions/{sid}/end').status_code==200
    assert answer(s,d,1).status_code==409
    assert s.get('/api/english/profile').json()['completed_samples']==0
    with a.db() as c:
        uid=s.get('/api/me').json()['id']
        assert c.execute('SELECT COUNT(*) FROM attempts WHERE user_id=?',(uid,)).fetchone()[0]==0


def test_profile_adapts_after_three_completed_sessions():
    s=student('enprofile100')
    text='In my project I work on a small robot that can carry heavy things, and I like building it with my team.'
    for _ in range(3):
        d=start(s)
        for i in range(3): assert answer(s,d,i,text).status_code==200
        assert s.post(f'/api/english/sessions/{d["id"]}/end').status_code==200
    p=s.get('/api/english/profile').json()
    assert p['completed_samples']==3 and p['mode']=='stretch'
    assert p['inferred_interests']==['engineering']
    assert p['spoken_turns']==0 and p['recent_speech']==[]
    rows=teacher().get('/api/teacher/english/students').json()
    assert any(r['student_no']=='enprofile100' and r['profile']['completed_samples']==3 for r in rows)


def test_ai_failure_fallback_and_grounded_corrections(monkeypatch):
    s=student('enfallback100')
    # Guarantee the configured path independently of preceding test order.
    teacher().post('/api/teacher/ai-settings',json={'base_url':'https://example.invalid/v1','model':'test','key':'dummy'})
    monkeypatch.setattr(a,'ai_call',lambda *args: {'reply':'Hello! What are you working on?','hint':'从 I work on… 开始','corrections':[{'quote':'I is','suggestion':'I am','reason':'搭配'},{'quote':'made up','suggestion':'x','reason':'x'}],'score':99})
    d=start(s);r=answer(s,d,0,'I is working on a robot.').json()
    details=r['turns'][-1]['details']
    assert len(details['corrections'])==1 and 'score' not in details
    def fail(*args):raise ValueError('upstream secret error')
    monkeypatch.setattr(a,'ai_call',fail)
    r=answer(s,d,1).json()
    assert '固定问答' in r['turns'][-1]['details']['notice']
    assert 'secret' not in json.dumps(r)


def test_audio_ticket_owner_expiry_single_use_and_edited_metrics(monkeypatch):
    s=student('envoice100');other=student('envoice200');d=start(s)
    fake={'text':'I make robots.','words':[{'w':'I','start_ms':0,'end_ms':200}],
        'metrics':{'word_count':3,'speech_rate_wpm':60.0,'pause_ratio':0.1},'model':'mock','duration_ms':3000}
    monkeypatch.setattr(speech,'transcribe',lambda *args:fake)
    r=s.post('/api/english/transcribe',files={'file':('a.wav',b'audio')});assert r.status_code==200
    ticket=r.json()['transcription_id']
    theirs=start(other)
    body={'text':'I build robots.','transcription_id':ticket,'request_id':'voice-answer-one','expected_turns':0}
    assert other.post(f'/api/english/sessions/{theirs["id"]}/turn',json=body).status_code==400
    r=s.post(f'/api/english/sessions/{d["id"]}/turn',json=body)
    assert r.status_code==200,r.text
    saved=r.json()['turns'][1]['details']['speech']
    assert saved['transcript_edited'] and saved['metrics']==fake['metrics']
    body.update(expected_turns=1,request_id='voice-answer-two')
    assert s.post(f'/api/english/sessions/{d["id"]}/turn',json=body).status_code==400
    r=s.post('/api/english/transcribe',files={'file':('a.wav',b'audio')})
    token=r.json()['transcription_id']
    with a.db() as c:c.execute('UPDATE english_transcriptions SET created=? WHERE id=?',(time.time()-1900,token))
    body.update(transcription_id=token)
    assert s.post(f'/api/english/sessions/{d["id"]}/turn',json=body).status_code==400
    assert s.post('/api/english/transcribe',files={'file':('a.wav',b'x'*5_000_001)}).status_code==413


def test_speech_not_enabled_and_no_untrusted_metrics(tmp_path):
    with pytest.raises(Exception) as exc:speech.transcribe(b'audio',tmp_path)
    assert exc.value.status_code==503
    s=student('enmetrics100');d=start(s)
    body={'text':'Hello there','expected_turns':0,'request_id':'invented-stats','metrics':{'speech_rate_wpm':999}}
    r=s.post(f'/api/english/sessions/{d["id"]}/turn',json=body).json()
    assert r['turns'][1]['details']['speech'] is None


def test_dated_news_filters_links_and_xml():
    current=datetime.now(timezone.utc)
    def item(title,date,link='https://www.bbc.com/news/technology-test'):
        return f'<item><title>{title}</title><pubDate>{format_datetime(date)}</pubDate><link>{link}</link></item>'
    raw=('<rss><channel>'+item('New robotics story',current)+item('Old story',current-timedelta(days=8))+item('Future story',current+timedelta(days=1))+item('Bad link',current,'https://evil.example/')+'<item><title>No date</title></item></channel></rss>').encode()
    result=en.parse_feed(raw,'technology','BBC',current)
    assert len(result)==1 and result[0]['title']=='New robotics story'
    assert not en.valid_news_link('https://bbc.com.evil.example/x','technology')
    with pytest.raises(ValueError):en.parse_feed(b'<!DOCTYPE rss><rss/>','technology','BBC')


def test_news_refresh_cached_and_failure_label(monkeypatch):
    s=student('ennews100');t=teacher()
    current=datetime.now(timezone.utc)
    raw=f'<rss><channel><item><title>Recent robot research</title><link>https://www.bbc.com/news/test</link><pubDate>{format_datetime(current)}</pubDate></item></channel></rss>'.encode()
    class Stream:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        def iter_bytes(self):yield raw
    class Client:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,*args):return Stream()
    monkeypatch.setattr(en.httpx,'Client',Client)
    r=t.post('/api/english/news/refresh');assert r.status_code==200,r.text
    assert r.json()['updated'] and r.json()['topics']
    assert any(x['kind']=='news' for x in s.get('/api/english/topics').json()['topics'])
    # A failed refresh keeps dated cache and exposes the failed-source state.
    class Failure(Client):
        def stream(self,*args):raise OSError('offline')
    monkeypatch.setattr(en.httpx,'Client',Failure)
    with a.db() as c:c.execute('UPDATE english_news SET checked=0')
    r=t.post('/api/english/news/refresh').json()
    assert r['error'] and r['topics']
