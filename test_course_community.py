import pytest
from test_course_admin import setup
from test_app import a,client


def uid(s):return s.get('/api/me').json()['id']
def grant(t,ids,courses):return t.post('/api/teacher/students/batch-courses',json={'student_ids':ids,'courses':courses})
def post(s,cid='writing',body='请问本周的课程任务是什么？',parent=None):return s.post(f'/api/courses/{cid}/messages',json={'body':body,'parent_id':parent})


def test_bulk_grant_additive_atomic_idempotent(setup):
    t,s,o=setup;ids=[uid(s),uid(o)]
    for i in ids:assert t.put(f'/api/teacher/students/{i}/courses',json={'courses':['writing']}).status_code==200
    assert grant(s,ids,['english']).status_code==403
    assert grant(t,ids+[999999],['english']).status_code==409
    assert s.get('/api/me').json()['courses']==['writing']
    result=grant(t,ids,['english','design']);assert result.status_code==200,result.text
    assert result.json()['added']==4
    assert set(s.get('/api/me').json()['courses'])=={'writing','english','design'}
    assert grant(t,ids,['english','design']).json()['added']==0
    assert grant(t,ids,['fake']).status_code==400
    assert grant(t,[],['english']).status_code==422
    assert grant(t,ids,[]).status_code==422
    assert grant(t,[True],['english']).status_code==422
    assert grant(t,[uid(t)],['english']).status_code==409
    with a.db() as c:assert c.execute("SELECT COUNT(*) FROM audit WHERE action='batch-course-grant'").fetchone()[0]==2

@pytest.mark.parametrize('cid',['writing','english','equipment','design'])
def test_board_membership_replies_and_moderation(setup,cid):
    t,s,o=setup;path=f'/api/courses/{cid}/messages'
    assert client().get(path).status_code==401
    r=post(s,cid);assert r.status_code==200,r.text
    mid=r.json()['id'];reply=post(t,cid,'教师回复：请查看课程任务。',mid);assert reply.status_code==200
    rows=o.get(path).json()['items'];assert rows[0]['replies']==1
    assert not rows[0]['can_delete']
    assert 'phone' not in rows[0] and 'student_no' not in rows[0] and 'user_id' not in rows[0]
    details=s.get(path+f'?parent_id={mid}').json();assert details['parent']['id']==mid and details['items'][0]['teacher']
    assert o.delete(path+f'/{mid}').status_code==403
    assert t.put(f'/api/teacher/students/{uid(o)}/courses',json={'courses':[]}).status_code==200
    assert o.get(path).status_code==403 and post(o,cid).status_code==403
    assert o.get(path+f'?parent_id={mid}').status_code==403
    assert s.delete(path+f'/{mid}').status_code==200
    assert s.get(path).json()['items']==[]
    assert s.get(path+f'?parent_id={mid}').status_code==404
    assert post(t,cid,parent=mid).status_code==404


def test_board_validation_cross_course_and_migration(setup):
    t,s,o=setup
    assert post(s,body='  ').status_code==400
    assert post(s,body='x'*2001).status_code==422
    assert post(s,'fake').status_code==404
    mid=post(s,'writing').json()['id']
    assert post(s,'english',parent=mid).status_code==404
    assert t.delete(f'/api/courses/english/messages/{mid}').status_code==404
    reply=post(s,parent=mid).json()['id']
    assert post(s,parent=reply).status_code==404
    assert t.delete(f'/api/courses/writing/messages/{reply}').status_code==200
    a.init();a.init()
    assert s.get('/api/courses/writing/messages').json()['items'][0]['id']==mid
    assert s.get('/api/courses/english/messages').json()['items']==[]


def test_board_pagination(setup):
    t,s,o=setup
    with a.db() as c:
        c.executemany('INSERT INTO course_messages(course_id,user_id,body,created) VALUES(?,?,?,?)',[('design',uid(s),str(i),a.now()) for i in range(35)])
    first=s.get('/api/courses/design/messages').json()
    assert len(first['items'])==30 and first['next']
    second=s.get('/api/courses/design/messages?before='+str(first['next'])).json()
    assert len(second['items'])==5 and second['next'] is None
    assert not {i['id'] for i in first['items']}&{i['id'] for i in second['items']}
