import json,sqlite3
import pytest
from test_app import a,student,teacher,client,doc

@pytest.fixture
def setup(tmp_path,monkeypatch):
    with sqlite3.connect(a.DB) as source,sqlite3.connect(tmp_path/'admin.db') as target:source.backup(target)
    monkeypatch.setattr(a,'DB',tmp_path/'admin.db');a.init()
    monkeypatch.setattr(a,'ai_settings',lambda:{'key':'','model':''})
    return teacher(),student('admin-student'),student('admin-other')

def invitation(t,course='writing',capacity=5):
    r=t.post('/api/teacher/invites',json={'label':'权限测试','max_uses':capacity,'valid_days':1,'course_id':course})
    assert r.status_code==200,r.text
    return r.json()['code']

def register(no,code,phone='13800138001'):
    c=client();r=c.post('/api/register',json={'name':'同名学生','student_no':no,'password':'test-password-123','invite_code':code,'phone':phone})
    assert r.status_code==200,r.text
    assert c.post('/api/login',json={'student_no':no,'password':'test-password-123'}).status_code==200
    return c

def test_phone_required_normalized_and_private(setup):
    t,s,other=setup;code=invitation(t)
    body={'name':'新同学','student_no':'phone-one','password':'test-password-123','invite_code':code}
    assert client().post('/api/register',json=body).status_code==422
    assert client().post('/api/register',json={**body,'phone':'not-a-phone'}).status_code==400
    new=register('phone-one',code,'+86 13800138001')
    assert new.get('/api/me').json()['phone']=='+8613800138001'
    assert s.get('/api/teacher/students').status_code==403
    assert new.post('/api/account/phone',json={'phone':'0731-12345678'}).status_code==200
    uid=new.get('/api/me').json()['id']
    row=next(r for r in t.get('/api/teacher/students').json() if r['id']==uid)
    assert row['phone']=='073112345678'


def test_invitation_grants_one_course_and_backend_enforces_scope(setup):
    t,s,other=setup;new=register('scope-one',invitation(t,'english'))
    assert new.get('/api/me').json()['courses']==['english']
    assert new.get('/api/english/profile').status_code==200
    for path in ['/api/chapters','/api/assignments','/api/practice/session','/courses/design/gomoku/']:
        assert new.get(path).status_code==403,path
    catalog=new.get('/api/courses').json()
    assert {r['id'] for r in catalog if r['enrolled']}=={'english'}
    code=invitation(t,'writing',1)
    assert new.post('/api/courses/join',json={'invite_code':code}).status_code==200
    assert new.post('/api/courses/join',json={'invite_code':code}).status_code==200
    assert new.get('/api/chapters').status_code==200
    row=next(r for r in t.get('/api/teacher/access').json()['invites'] if r['course_id']=='writing' and r['max_uses']==1)
    assert row['uses']==1
    assert new.post('/api/courses/join',json={'invite_code':invitation(t,'design')}).status_code==200
    assert new.get('/courses/design/gomoku/').status_code==200
    assert t.get('/api/chapters').status_code==200


def test_course_authority_can_be_revoked_without_losing_ppt_evidence(setup):
    t,s,other=setup;uid=s.get('/api/me').json()['id']
    path=f'/api/teacher/students/{uid}/presentation/writing'
    assert s.put(path,json={'presented':True}).status_code==403
    assert t.put(path,json={'presented':True,'date':'2026-11-10','topic':'用AI做文献矩阵'}).status_code==200
    assert t.put(f'/api/teacher/students/{uid}/courses',json={'courses':['english']}).status_code==200
    assert s.get('/api/chapters').status_code==403 and s.get('/api/english/profile').status_code==200
    assert t.put(path,json={'presented':False}).status_code==409
    assert t.put(f'/api/teacher/students/{uid}/courses',json={'courses':['writing','english']}).status_code==200
    row=next(x for x in t.get('/api/teacher/students').json() if x['id']==uid)
    mark=next(x for x in row['courses'] if x['course_id']=='writing')
    assert mark['ppt_presented']==1 and mark['ppt_topic']=='用AI做文献矩阵'
    assert t.put(path,json={'presented':True,'date':'bad-date'}).status_code==400
    assert t.put(path,json={'presented':False}).status_code==200
    csv=t.get('/api/teacher/export').text
    assert '电话号码' in csv and 'AI科研PPT分享' in csv


def test_delete_removes_login_frees_student_number_and_preserves_work(setup):
    t,s,other=setup;uid=s.get('/api/me').json()['id']
    aid=t.post('/api/assignments',json={'title':'归档作业','instructions':'提交一份文档'}).json()['id']
    assert s.post('/api/submissions',data={'assignment_id':aid},files={'file':('draft.docx',doc())}).status_code==200
    assert s.request('DELETE',f'/api/teacher/students/{uid}',json={'student_no':'admin-student','reason':'重复账号'}).status_code==403
    assert t.request('DELETE',f'/api/teacher/students/{uid}',json={'student_no':'wrong','reason':'重复账号'}).status_code==409
    assert t.request('DELETE',f'/api/teacher/students/{uid}',json={'student_no':'admin-student','reason':'重复账号'}).status_code==200
    assert s.get('/api/me').status_code==401
    with pytest.raises(a.HTTPException) as blocked:a.reserve_ai_call(uid)
    assert blocked.value.status_code==403
    assert t.post(f'/api/teacher/students/{uid}/password',json={'password':'new-password-123'}).status_code==404
    assert client().post('/api/login',json={'student_no':'admin-student','password':'test-password-123'}).status_code==401
    assert all(r['id']!=uid for r in t.get('/api/teacher/students').json())
    assert all(r['user_id']!=uid for r in t.get('/api/teacher/submissions').json())
    new=register('admin-student',invitation(t))
    assert new.get('/api/me').json()['id']!=uid
    assert not next(r for r in new.get('/api/assignments').json() if r['id']==aid)['submission']
    with a.db() as c:
        assert c.execute('SELECT 1 FROM submissions WHERE user_id=?',(uid,)).fetchone()
        assert c.execute("SELECT 1 FROM audit WHERE action='student-delete'").fetchone()


def test_existing_authority_migrates_once_and_teacher_cannot_be_deleted(setup):
    import course_access
    t,s,other=setup;uid=s.get('/api/me').json()['id'];tid=t.get('/api/me').json()['id']
    with a.db() as c:
        c.execute("DELETE FROM account_migrations WHERE version='course-access-v1'")
        c.execute('DELETE FROM course_memberships WHERE user_id=?',(uid,))
        course_access.migrate(c,a.now())
        assert len(course_access.courses_for(c,uid))==4
        c.execute("UPDATE course_memberships SET active=0 WHERE user_id=? AND course_id='english'",(uid,))
        course_access.migrate(c,a.now())
        assert len(course_access.courses_for(c,uid))==3
    assert t.request('DELETE',f'/api/teacher/students/{tid}',json={'student_no':'teacher','reason':'不应删除'}).status_code==404


def test_course_permissions_payload_validation(setup):
    t,s,other=setup;uid=s.get('/api/me').json()['id']
    assert t.put(f'/api/teacher/students/{uid}/courses',json={'courses':['writing','writing']}).status_code==400
    assert t.put(f'/api/teacher/students/{uid}/courses',json={'courses':['unknown']}).status_code==400
    assert t.post('/api/teacher/invites',json={'course_id':'unknown'}).status_code==422
    assert s.post('/api/teacher/invites',json={'course_id':'english'}).status_code==403
