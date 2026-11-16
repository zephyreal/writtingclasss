from test_app import teacher,student,client,a

def test_login_role_is_checked_before_session_created():
    t=teacher();s=student('role-entry-student')
    with a.db() as db:teacher_no=db.execute("SELECT student_no FROM users WHERE role='teacher' ORDER BY id LIMIT 1").fetchone()[0]
    c=client()
    response=c.post('/api/login',json={'student_no':'role-entry-student','password':'test-password-123','role':'teacher'})
    assert response.status_code==403 and 'session' not in response.cookies
    assert c.post('/api/login',json={'student_no':'role-entry-student','password':'test-password-123','role':'student'}).status_code==200
    assert c.get('/api/teacher/students').status_code==403
    assert c.post('/api/login',json={'student_no':'role-entry-student','password':'test-password-123','role':'admin'}).status_code==422
    assert c.post('/api/login',json={'student_no':teacher_no,'password':'teacher-password-123','role':'student'}).status_code==403
    assert c.post('/api/login',json={'student_no':teacher_no,'password':'teacher-password-123','role':'teacher'}).status_code==200
