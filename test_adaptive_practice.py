import json
import sqlite3
from collections import Counter
import pytest
from test_app import a,student,teacher
import adaptive_practice as p
from practice_bank import BANK,TOPICS,SOURCES,LEVELS,load_bank

@pytest.fixture
def context(tmp_path,monkeypatch):
    with sqlite3.connect(a.DB) as source,sqlite3.connect(tmp_path/'practice.db') as target:source.backup(target)
    monkeypatch.setattr(a,'DB',tmp_path/'practice.db');a.init()
    timer=[1800000000.0];monkeypatch.setattr(p,'clock',lambda:timer[0])
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'','model':''})
    t,s,other=teacher(),student('timed01'),student('timed02')
    return t,s,other,timer

def start(s):
    r=s.post('/api/practice/session');assert r.status_code==200,r.text
    return r.json()

def correct_choice(active):
    q=BANK[active['question']['id']]
    return active['question']['options'].index(q['options'][q['answer']])

def finish(s,timer,active=None,wrong=False):
    active=active or start(s)
    for i in range(active['position'],30):
        timer[0]+=.3
        choice=correct_choice(active)
        if wrong:choice=(choice+1)%len(active['question']['options'])
        r=s.post('/api/practice/session/'+active['token']+'/answer',json={'position':i,'choice':choice})
        assert r.status_code==200,r.text
        d=r.json()
        if i<29:assert not d['finished'];active=d['active']
        else:assert d['finished'];return d['result'],active

def test_bank_shape_levels_and_no_duplicate_stems():
    assert len(BANK)==640 and len(TOPICS)==64
    for unit in range(1,9):
        qs=[q for q in BANK.values() if q['chapter_id']==unit]
        assert len(qs)==80
        assert Counter(q['kind'] for q in qs)=={'choice':56,'boolean':24}
        assert Counter(q['level'] for q in qs)=={1:24,2:40,3:16}
        assert all(q['source'] in SOURCES and q['explanation'] for q in qs)
        assert all(len(q['options'])==(3 if q['kind']=='choice' else 2) for q in qs)
        # These short items fit the requested ten-second interaction, not long reading cases.
        assert max(len(q['stem'])+sum(map(len,q['options'])) for q in qs)<=70
    assert len({q['stem'] for q in BANK.values()})==640
    assert all(len(set(q['options']))==len(q['options']) for q in BANK.values())
    assert load_bank()[1]==p.BANK_VERSION


def test_first_round_covers_eight_units_and_no_answers_leaked(context):
    t,s,other,timer=context
    active=start(s)
    assert active['total']==30 and active['seconds']==10 and active['source']=='random'
    assert not any(k in active['question'] for k in ('answer','explanation','level','topic','source'))
    with a.db() as c:
        row=c.execute('SELECT * FROM practice_pending WHERE token=?',(active['token'],)).fetchone()
        qs=json.loads(row['items']);counts=Counter(q['chapter_id'] for q in qs)
        assert sorted(counts.values())==[3,3,4,4,4,4,4,4]
        assert len({q['id'] for q in qs})==30
    assert other.post('/api/practice/session/'+active['token']+'/answer',json={'position':0,'choice':0}).status_code==404
    resumed=start(s)
    assert resumed==active  # starting/refreshing cannot reroll or extend a deadline
    timer[0]+=1
    assert start(s)['deadline']==active['deadline']


def test_partial_has_no_record_and_abandon_discards(context):
    t,s,other,timer=context
    active=start(s)
    for i in range(9):
        r=s.post('/api/practice/session/'+active['token']+'/answer',json={'position':i,'choice':correct_choice(active)}).json()
        active=r['active']
    uid=s.get('/api/me').json()['id']
    state=s.get('/api/practice/session').json()
    assert state['summary']['rounds']==0 and not state['records']
    assert not t.get('/api/teacher/practice/students/'+str(uid)).json()['records']
    assert s.delete('/api/practice/session/'+active['token']).status_code==200
    assert s.get('/api/practice/session').json()['active'] is None
    assert start(s)['source']=='random'


def test_complete_atomic_idempotent_record_and_legacy_unchanged(context):
    t,s,other,timer=context
    legacy=s.get('/api/progress').json()
    r,last=finish(s,timer)
    assert r['correct']==30 and r['score']==100 and r['timeouts']==0 and len(r['items'])==30
    assert all(q['correct'] for q in r['items'])
    assert s.get('/api/progress').json()==legacy
    assert s.get('/api/practice/session').json()['summary']['rounds']==1
    assert other.get('/api/practice/records/'+str(r['id'])).status_code==404
    replay=s.post('/api/practice/session/'+last['token']+'/answer',json={'position':29,'choice':0}).json()
    assert replay['result']['id']==r['id']
    assert s.get('/api/practice/session').json()['summary']['rounds']==1
    assert s.get('/api/profile').json()['timed_practice']['rounds']==1
    new=start(s);assert new['source']=='rules'


def test_timeout_server_enforcement_and_stale_replay(context):
    t,s,other,timer=context
    active=start(s);token=active['token']
    assert s.post('/api/practice/session/'+token+'/answer',json={'position':0,'choice':None}).status_code==409
    timer[0]=active['deadline']+.01
    r=s.post('/api/practice/session/'+token+'/answer',json={'position':0,'choice':correct_choice(active)}).json()
    next_active=r['active'];assert next_active['position']==1
    old=s.post('/api/practice/session/'+token+'/answer',json={'position':0,'choice':0}).json()
    assert old['active']['position']==1 and old['active']['deadline']==next_active['deadline']
    out,_=finish(s,timer,next_active)
    assert out['timeouts']==1 and out['correct']==29
    assert out['items'][0]['choice'] is None and out['items'][0]['timed_out']
    assert s.post('/api/practice/session/'+token+'/answer',json={'position':True,'choice':False}).status_code==422


def test_invalid_options_and_positions(context):
    t,s,other,timer=context
    active=start(s)
    assert s.post('/api/practice/session/'+active['token']+'/answer',json={'position':1,'choice':0}).status_code==409
    assert s.post('/api/practice/session/'+active['token']+'/answer',json={'position':0,'choice':3}).status_code==422
    with a.db() as c:
        row=c.execute('SELECT items FROM practice_pending WHERE token=?',(active['token'],)).fetchone()
        items=json.loads(row[0]);items[0]={**next(q for q in BANK.values() if q['kind']=='boolean')}
        c.execute('UPDATE practice_pending SET items=? WHERE token=?',(json.dumps(items),active['token']))
    assert s.post('/api/practice/session/'+active['token']+'/answer',json={'position':0,'choice':2}).status_code==400


def test_expired_session_never_saved(context):
    t,s,other,timer=context
    active=start(s);timer[0]+=1201
    assert s.get('/api/practice/session').json()['active'] is None
    assert s.post('/api/practice/session/'+active['token']+'/answer',json={'position':0,'choice':0}).status_code==404
    assert s.get('/api/practice/session').json()['summary']['rounds']==0


def test_teacher_delete_reset_permissions_audit_and_recommendation(context):
    t,s,other,timer=context
    first,_=finish(s,timer,wrong=True);second,_=finish(s,timer)
    uid=s.get('/api/me').json()['id']
    assert s.get('/api/teacher/practice/students').status_code==403
    assert other.request('DELETE','/api/teacher/practice/records/'+str(first['id']),json={'reason':'随意删除'}).status_code==403
    assert t.get('/api/teacher/practice/records/'+str(first['id'])).json()['score']==0
    active=start(s)
    r=t.request('DELETE','/api/teacher/practice/records/'+str(first['id']),json={'reason':'测试作答删除'})
    assert r.status_code==200,r.text
    assert s.get('/api/practice/session').json()['summary']['rounds']==1
    assert s.get('/api/practice/session').json()['active'] is None
    assert s.get('/api/practice/records/'+str(first['id'])).status_code==404
    assert t.post('/api/teacher/practice/students/'+str(uid)+'/reset',json={'reason':'重新诊断'}).status_code==200
    assert s.get('/api/practice/session').json()['summary']['rounds']==0
    assert start(s)['source']=='random'
    with a.db() as c:assert c.execute("SELECT COUNT(*) FROM audit WHERE action IN ('practice-delete','practice-reset')").fetchone()[0]==2
    assert s.get('/api/me').status_code==200  # reset only this practice module


def test_model_plan_is_closed_validated_and_quota_failure_falls_back(context,monkeypatch):
    t,s,other,timer=context;calls=[]
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'test-only','model':'mock'})
    def ai(system,payload):
        calls.append(payload)
        return {'topics':[payload['performance'][0]['id']],'level':1}
    monkeypatch.setattr(a,'ai_call',ai)
    r,_=finish(s,timer,wrong=True)
    assert len(calls)==1 and calls[0]['_usage_context']['user_id']==s.get('/api/me').json()['id']
    assert 'student_no' not in json.dumps(calls) and 'name' not in json.dumps(calls[0]['_usage_context'])
    assert start(s)['source']=='ai'
    s.delete('/api/practice/session/'+s.get('/api/practice/session').json()['active']['token'])
    monkeypatch.setattr(a,'ai_call',lambda *args:{'topics':['invented-topic'],'level':9})
    r,_=finish(s,timer)
    assert start(s)['source']=='rules'
    active=s.get('/api/practice/session').json()['active'];s.delete('/api/practice/session/'+active['token'])
    def unavailable(*args):raise RuntimeError('simulated provider failure')
    monkeypatch.setattr(a,'ai_call',unavailable)
    finish(s,timer)
    assert start(s)['source']=='rules'


def test_reset_during_model_call_cannot_restore_old_plan(context,monkeypatch):
    t,s,other,timer=context;uid=s.get('/api/me').json()['id']
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'test-only','model':'mock'})
    def ai(system,payload):
        t.post('/api/teacher/practice/students/'+str(uid)+'/reset',json={'reason':'正在重新诊断'})
        return {'topics':[payload['performance'][0]['id']],'level':1}
    monkeypatch.setattr(a,'ai_call',ai)
    finish(s,timer)
    assert s.get('/api/practice/session').json()['summary']['rounds']==0
    assert start(s)['source']=='random'


def test_last_answer_commit_failure_does_not_leave_partial_record(context):
    t,s,other,timer=context;active=start(s)
    for i in range(29):
        active=s.post('/api/practice/session/'+active['token']+'/answer',json={'position':i,'choice':correct_choice(active)}).json()['active']
    with a.db() as c:c.execute("CREATE TRIGGER fail_practice BEFORE INSERT ON practice_runs BEGIN SELECT RAISE(ABORT,'simulated storage failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        s.post('/api/practice/session/'+active['token']+'/answer',json={'position':29,'choice':correct_choice(active)})
    with a.db() as c:
        assert c.execute('SELECT COUNT(*) FROM practice_runs').fetchone()[0]==0
        assert c.execute('SELECT position FROM practice_pending WHERE token=?',(active['token'],)).fetchone()[0]==29
        c.execute('DROP TRIGGER fail_practice')
    out,_=finish(s,timer,active);assert out['correct']==30


def test_recommendation_allocates_focus_items_and_keeps_unit_coverage(context):
    t,s,other,timer=context;uid=s.get('/api/me').json()['id']
    weak={'u1-t1','u2-t1','u3-t1'}
    items=[]
    for topic in weak:
        for q in [q for q in BANK.values() if q['topic']==topic][:6]:items.append({**q,'choice':None,'correct':False,'timed_out':False})
    for q in [q for q in BANK.values() if q['chapter_id'] in (4,5,6,7,8)][:12]:items.append({**q,'choice':q['answer'],'correct':True,'timed_out':False})
    with a.db() as c:
        c.execute('INSERT INTO practice_runs(token,user_id,started,completed,source,correct,timeouts,items,bank_version) VALUES(?,?,?,?,?,?,?,?,?)',('fixture',uid,timer[0]-100,timer[0],'random',12,0,json.dumps(items),p.BANK_VERSION))
        qs,source=p.choose(c,uid)
    assert source=='rules' and len(qs)==30 and len({q['id'] for q in qs})==30
    assert len({q['chapter_id'] for q in qs})==8
    assert sum(q['topic'] in weak for q in qs)>=14
