from test_course_admin import setup
from test_app import a,client
import course_access

IDENTITY={'student_no':'admin-student','phone':'13800138000'}

def issue(t,s):
    c=client();uid=s.get('/api/me').json()['id']
    assert c.post('/api/password-recovery/request',json=IDENTITY).status_code==200
    r=t.post(f'/api/teacher/password-recovery/{uid}/approve',json={'verified':True})
    assert r.status_code==200,r.text
    return c,uid,r.json()['code']

def test_recovery_requires_teacher_and_single_use(setup):
    t,s,other=setup;c=client();uid=s.get('/api/me').json()['id']
    unknown=c.post('/api/password-recovery/request',json={**IDENTITY,'phone':'13800138099'})
    good=c.post('/api/password-recovery/request',json=IDENTITY)
    assert unknown.json()==good.json()
    assert s.get('/api/teacher/password-recovery').status_code==403
    assert c.get('/api/teacher/password-recovery').status_code==401
    assert s.post(f'/api/teacher/password-recovery/{uid}/approve',json={'verified':True}).status_code==403
    assert t.post(f'/api/teacher/password-recovery/{uid}/approve',json={'verified':False}).status_code==400
    rows=t.get('/api/teacher/password-recovery').json()
    assert len(rows)==1 and 'code_hash' not in rows[0] and 'password_version' not in rows[0]
    code=t.post(f'/api/teacher/password-recovery/{uid}/approve',json={'verified':True}).json()['code']
    body={**IDENTITY,'code':code,'password':'new-password-123'}
    assert c.post('/api/password-recovery/reset',json={**body,'code':'bad'}).status_code==400
    # A repeat request cannot invalidate the teacher's code.
    c.post('/api/password-recovery/request',json=IDENTITY)
    assert c.post('/api/password-recovery/reset',json=body).status_code==200
    assert s.get('/api/me').status_code==401
    assert other.get('/api/me').status_code==200
    assert c.post('/api/password-recovery/reset',json=body).status_code==400
    assert c.post('/api/login',json={'student_no':IDENTITY['student_no'],'password':'test-password-123'}).status_code==401
    assert c.post('/api/login',json={'student_no':IDENTITY['student_no'],'password':body['password']}).status_code==200
    assert not t.get('/api/teacher/password-recovery').json()


def test_expiry_and_password_change_invalidate_code(setup):
    t,s,other=setup;c,uid,code=issue(t,s)
    with a.db() as db:db.execute('UPDATE password_recovery SET expires=0 WHERE user_id=?',(uid,))
    body={**IDENTITY,'code':code,'password':'new-password-123'}
    assert c.post('/api/password-recovery/reset',json=body).status_code==400
    c,uid,code=issue(t,s)
    t.post(f'/api/teacher/students/{uid}/password',json={'password':'teacher-reset-123'})
    assert c.post('/api/password-recovery/reset',json={**body,'code':code}).status_code==400


def test_phone_change_reissue_and_throttle(setup):
    t,s,other=setup;c,uid,old=issue(t,s)
    code=t.post(f'/api/teacher/password-recovery/{uid}/approve',json={'verified':True}).json()['code']
    body={**IDENTITY,'code':old,'password':'new-password-123'}
    assert c.post('/api/password-recovery/reset',json=body).status_code==400
    s.post('/api/account/phone',json={'phone':'13800138099'})
    assert c.post('/api/password-recovery/reset',json={**body,'code':code}).status_code==400
    for _ in range(3):assert c.post('/api/password-recovery/reset',json=body).status_code==400
    assert c.post('/api/password-recovery/reset',json=body).status_code==429
