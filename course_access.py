"""Course enrolment, contact details and reversible student account removal."""
import hmac
import hashlib
import json
import re
import secrets
import time
from fastapi import Depends,HTTPException,Query,Request
from pydantic import BaseModel,Field,StrictInt

COURSE_IDS=('writing','english','equipment','design')
TITLES=dict(zip(COURSE_IDS,('学术论文写作','机械工程专业英语','智能装备基础','智能制造课程设计')))

def phone_value(value):
    phone=re.sub(r'[\s()\-]','',value.strip())
    if not re.fullmatch(r'\+?[0-9]{7,15}',phone):raise HTTPException(400,'请填写有效电话号码，支持7—15位数字和国际区号')
    return phone

def migrate(c,stamp):
    cols={r['name'] for r in c.execute('PRAGMA table_info(users)')}
    for name,definition in [('phone',"TEXT NOT NULL DEFAULT ''"),('deleted_at',"TEXT NOT NULL DEFAULT ''"),('archived_student_no',"TEXT NOT NULL DEFAULT ''")]:
        if name not in cols:c.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
    cols={r['name'] for r in c.execute('PRAGMA table_info(course_invites)')}
    if 'course_id' not in cols:c.execute("ALTER TABLE course_invites ADD COLUMN course_id TEXT NOT NULL DEFAULT 'writing'")
    c.execute('''CREATE TABLE IF NOT EXISTS course_memberships(user_id INTEGER REFERENCES users(id),course_id TEXT NOT NULL,
        joined TEXT NOT NULL,origin TEXT NOT NULL,ppt_presented INTEGER NOT NULL DEFAULT 0,ppt_date TEXT NOT NULL DEFAULT '',
        ppt_topic TEXT NOT NULL DEFAULT '',PRIMARY KEY(user_id,course_id))''')
    membership_columns={r['name'] for r in c.execute('PRAGMA table_info(course_memberships)')}
    if 'active' not in membership_columns:c.execute('ALTER TABLE course_memberships ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
    c.execute("""CREATE TABLE IF NOT EXISTS course_messages(
        id INTEGER PRIMARY KEY,course_id TEXT NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),
        parent_id INTEGER REFERENCES course_messages(id),body TEXT NOT NULL,created TEXT NOT NULL,
        deleted INTEGER NOT NULL DEFAULT 0)""")
    c.execute('CREATE INDEX IF NOT EXISTS course_messages_list ON course_messages(course_id,parent_id,deleted,id)')
    c.execute('''CREATE TABLE IF NOT EXISTS password_recovery(user_id INTEGER PRIMARY KEY REFERENCES users(id),requested REAL NOT NULL,expires REAL NOT NULL,code_hash TEXT NOT NULL DEFAULT '',password_version TEXT NOT NULL,phone TEXT NOT NULL)''')
    c.execute('CREATE TABLE IF NOT EXISTS account_migrations(version TEXT PRIMARY KEY,created TEXT NOT NULL)')
    if not c.execute("SELECT 1 FROM account_migrations WHERE version='course-access-v1'").fetchone():
        for u in c.execute("SELECT id FROM users WHERE role='student' AND deleted_at=''").fetchall():
            c.executemany('INSERT OR IGNORE INTO course_memberships(user_id,course_id,joined,origin) VALUES(?,?,?,?)',[(u['id'],cid,stamp,'历史账号权限保留') for cid in COURSE_IDS])
        c.execute("INSERT INTO account_migrations VALUES('course-access-v1',?)",(stamp,))

def courses_for(c,uid):
    return [dict(r) for r in c.execute('SELECT course_id,ppt_presented,ppt_date,ppt_topic,origin FROM course_memberships WHERE user_id=? AND active=1 ORDER BY course_id',(uid,))]

def require_course(c,u,cid):
    if u['role']=='teacher':return
    if not c.execute('SELECT 1 FROM course_memberships WHERE user_id=? AND course_id=? AND active=1',(u['id'],cid)).fetchone():raise HTTPException(403,'请先使用“'+TITLES[cid]+'”的邀请码加入课程')

def redeem(c,uid,code,stamp):
    invite=c.execute('SELECT * FROM course_invites WHERE code_hash=? AND revoked=0 AND expires>?',(hashlib.sha256(code.strip().encode()).hexdigest(),time.time())).fetchone()
    if not invite:raise HTTPException(403,'邀请码无效、已过期或已停用，请联系教师')
    if invite['course_id'] not in COURSE_IDS:raise HTTPException(403,'邀请码课程权限无效，请联系教师')
    if c.execute('SELECT 1 FROM course_memberships WHERE user_id=? AND course_id=? AND active=1',(uid,invite['course_id'])).fetchone():return invite['course_id']
    if invite['uses']>=invite['max_uses']:raise HTTPException(403,'邀请码名额已用完，请联系教师')
    c.execute('INSERT INTO course_memberships(user_id,course_id,joined,origin) VALUES(?,?,?,?) ON CONFLICT(user_id,course_id) DO UPDATE SET active=1,joined=excluded.joined,origin=excluded.origin',(uid,invite['course_id'],stamp,'邀请码加入'))
    c.execute('UPDATE course_invites SET uses=uses+1 WHERE id=?',(invite['id'],))
    return invite['course_id']

def gated_course(path):
    # Public navigation bootstrap is needed before login; it contains no course data.
    # Keep this exact: all racing pages, examples and results remain protected.
    if path=='/courses/design/vehicle/entry.js':return None
    if path.startswith('/api/arena/worker/'):return None  # Dedicated scoped bearer credentials, never browser sessions.
    if path=='/api/arena' or path.startswith('/api/arena/'):return 'design'
    if path.startswith('/api/english'):return 'english'
    if path.startswith('/courses/design/'):return 'design'
    if any(path==p or path.startswith(p+'/') for p in ('/api/chapters','/api/materials','/api/progress','/api/practice','/api/profile','/api/assignments','/api/submissions','/api/writing')):return 'writing'
    return None

class BatchGrant(BaseModel):
    student_ids:list[StrictInt]=Field(min_length=1,max_length=500)
    courses:list[str]=Field(min_length=1,max_length=4)
class Message(BaseModel):
    body:str=Field(min_length=1,max_length=2000)
    parent_id:StrictInt|None=None

class RecoveryIdentity(BaseModel):
    student_no:str=Field(min_length=1,max_length=30)
    phone:str=Field(min_length=7,max_length=30)
class RecoveryReset(RecoveryIdentity):
    code:str=Field(min_length=1,max_length=64)
    password:str=Field(min_length=10,max_length=128)
class RecoveryApproval(BaseModel):
    verified:bool

class Join(BaseModel):invite_code:str=Field(min_length=1,max_length=100)
class Phone(BaseModel):phone:str=Field(min_length=7,max_length=30)
class Memberships(BaseModel):courses:list[str]=Field(max_length=4)
class Presentation(BaseModel):
    presented:bool
    date:str=Field(default='',max_length=30)
    topic:str=Field(default='',max_length=200)
class Removal(BaseModel):
    student_no:str=Field(min_length=1,max_length=100)
    reason:str=Field(min_length=2,max_length=500)

def register(app,env):
    db=lambda:env['db']();current=env['current'];teacher=env['teacher']
    @app.post('/api/teacher/students/batch-courses')
    def grant_many(x:BatchGrant,u=Depends(teacher)):
        ids=set(x.student_ids);courses=set(x.courses)
        if any(uid<=0 for uid in ids) or any(cid not in COURSE_IDS for cid in courses):
            raise HTTPException(400,'请选择有效学生和课程')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            marks=','.join('?' for _ in ids)
            found={r[0] for r in c.execute(f"SELECT id FROM users WHERE id IN ({marks}) AND role='student' AND deleted_at=''",tuple(ids))}
            if found!=ids:raise HTTPException(409,'部分学生账号已变更，请刷新列表后重新选择；本次未修改权限')
            added=0
            for uid in sorted(ids):
                for cid in sorted(courses):
                    if c.execute('SELECT 1 FROM course_memberships WHERE user_id=? AND course_id=? AND active=1',(uid,cid)).fetchone():continue
                    c.execute('INSERT INTO course_memberships(user_id,course_id,joined,origin) VALUES(?,?,?,?) ON CONFLICT(user_id,course_id) DO UPDATE SET active=1,joined=excluded.joined,origin=excluded.origin',(uid,cid,env['now'](),'教师批量授权'))
                    added+=1
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'batch-course-grant',json.dumps({'students':sorted(ids),'courses':sorted(courses),'added':added}),env['now']()))
        return {'ok':True,'students':len(ids),'added':added}

    def board_access(c,u,cid):
        if cid not in COURSE_IDS:raise HTTPException(404,'课程不存在')
        require_course(c,u,cid)

    def message_row(r,u):
        return {'id':r['id'],'parent_id':r['parent_id'],'body':r['body'],'created':r['created'],
                'author':r['name'] if not r['deleted_at'] else '已注销用户',
                'teacher':r['role']=='teacher','can_delete':u['role']=='teacher' or r['user_id']==u['id']}

    @app.get('/api/courses/{cid}/messages')
    def messages(cid:str,before:int=Query(default=0,ge=0),parent_id:int|None=Query(default=None,gt=0),u=Depends(current)):
        with db() as c:
            board_access(c,u,cid)
            parent=None
            if parent_id is not None:
                parent=c.execute('SELECT m.*,u.name,u.role,u.deleted_at FROM course_messages m JOIN users u ON u.id=m.user_id WHERE m.id=? AND m.course_id=? AND m.parent_id IS NULL AND m.deleted=0',(parent_id,cid)).fetchone()
                if not parent:raise HTTPException(404,'留言不存在或已删除')
            rows=c.execute('SELECT m.*,u.name,u.role,u.deleted_at FROM course_messages m JOIN users u ON u.id=m.user_id WHERE m.course_id=? AND m.parent_id IS ? AND m.deleted=0 AND (?=0 OR m.id<?) ORDER BY m.id DESC LIMIT 31',(cid,parent_id,before,before)).fetchall()
            items=[]
            for r in rows[:30]:
                item=message_row(r,u)
                item['replies']=c.execute('SELECT COUNT(*) FROM course_messages WHERE parent_id=? AND deleted=0',(r['id'],)).fetchone()[0] if parent_id is None else 0
                items.append(item)
            return {'items':items,'next':rows[29]['id'] if len(rows)>30 else None,'parent':message_row(parent,u) if parent else None}

    @app.post('/api/courses/{cid}/messages')
    def post_message(cid:str,x:Message,u=Depends(current)):
        body=x.body.strip()
        if not body:raise HTTPException(400,'请输入留言内容')
        env['throttle']('course-message:'+str(u['id']),60,3600)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');board_access(c,u,cid)
            if x.parent_id is not None and not c.execute('SELECT 1 FROM course_messages WHERE id=? AND course_id=? AND parent_id IS NULL AND deleted=0',(x.parent_id,cid)).fetchone():
                raise HTTPException(404,'原留言不存在或已删除')
            mid=c.execute('INSERT INTO course_messages(course_id,user_id,parent_id,body,created) VALUES(?,?,?,?,?)',(cid,u['id'],x.parent_id,body,env['now']())).lastrowid
        return {'ok':True,'id':mid}

    @app.delete('/api/courses/{cid}/messages/{mid}')
    def delete_message(cid:str,mid:int,u=Depends(current)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');board_access(c,u,cid)
            row=c.execute('SELECT * FROM course_messages WHERE id=? AND course_id=? AND deleted=0',(mid,cid)).fetchone()
            if not row:raise HTTPException(404,'留言不存在或已删除')
            if u['role']!='teacher' and row['user_id']!=u['id']:raise HTTPException(403,'只能删除自己的留言')
            c.execute('UPDATE course_messages SET deleted=1 WHERE id=? OR parent_id=?',(mid,mid))
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'course-message-delete',str(mid),env['now']()))
        return {'ok':True}

    @app.post('/api/courses/join')
    def join(x:Join,u=Depends(current)):
        env['throttle']('course-join:'+str(u['id']),30,3600)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');cid=redeem(c,u['id'],x.invite_code,env['now']())
        env['audit'](u['id'],'join-course',cid);return {'ok':True,'course_id':cid}

    @app.post('/api/account/phone')
    def update_phone(x:Phone,u=Depends(current)):
        phone=phone_value(x.phone)
        with db() as c:c.execute('UPDATE users SET phone=? WHERE id=?',(phone,u['id']))
        return {'ok':True,'phone':phone}

    @app.put('/api/teacher/students/{uid}/courses')
    def memberships(uid:int,x:Memberships,u=Depends(teacher)):
        if len(set(x.courses))!=len(x.courses) or any(cid not in COURSE_IDS for cid in x.courses):raise HTTPException(400,'请选择有效课程，不可重复')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='student' AND deleted_at=''",(uid,)).fetchone():raise HTTPException(404,'学生不存在')
            existing={r[0] for r in c.execute('SELECT course_id FROM course_memberships WHERE user_id=? AND active=1',(uid,))}
            for cid in existing-set(x.courses):c.execute('UPDATE course_memberships SET active=0 WHERE user_id=? AND course_id=?',(uid,cid))
            for cid in set(x.courses)-existing:c.execute('INSERT INTO course_memberships(user_id,course_id,joined,origin) VALUES(?,?,?,?) ON CONFLICT(user_id,course_id) DO UPDATE SET active=1,joined=excluded.joined,origin=excluded.origin',(uid,cid,env['now'](),'教师授权'))
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'student-courses',json.dumps({'student':uid,'courses':x.courses}),env['now']()))
        return {'ok':True}

    @app.put('/api/teacher/students/{uid}/presentation/{cid}')
    def presentation(uid:int,cid:str,x:Presentation,u=Depends(teacher)):
        if cid not in COURSE_IDS:raise HTTPException(404,'课程不存在')
        if x.date:
            try:env['datetime'].fromisoformat(x.date)
            except ValueError:raise HTTPException(400,'请填写有效分享日期')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='student' AND deleted_at=''",(uid,)).fetchone():raise HTTPException(404,'学生不存在')
            n=c.execute('UPDATE course_memberships SET ppt_presented=?,ppt_date=?,ppt_topic=? WHERE user_id=? AND course_id=? AND active=1',(int(x.presented),(x.date or env['now']()[:10]) if x.presented else '',x.topic.strip() if x.presented else '',uid,cid)).rowcount
            if not n:raise HTTPException(409,'该学生尚未加入此课程')
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'student-ppt',json.dumps({'student':uid,'course':cid,'presented':x.presented}),env['now']()))
        return {'ok':True}

    @app.delete('/api/teacher/students/{uid}')
    def remove(uid:int,x:Removal,u=Depends(teacher)):
        # Keep teaching evidence; remove access and free the student number atomically.
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            student=c.execute("SELECT * FROM users WHERE id=? AND role='student' AND deleted_at=''",(uid,)).fetchone()
            if not student:raise HTTPException(404,'学生不存在或已经删除')
            if student['student_no']!=x.student_no.strip():raise HTTPException(409,'确认学号与当前账号不符，请重新核对')
            if not x.reason.strip():raise HTTPException(400,'请填写删除原因')
            if c.execute("SELECT 1 FROM submissions WHERE user_id=? AND (status='AI批改中' OR id IN (SELECT submission_id FROM paper_review_jobs WHERE state='running'))",(uid,)).fetchone():raise HTTPException(409,'该生作业正在批改，请等待结束后删除')
            # A queued job must never run after removal. Preserve its historical entry.
            c.execute("UPDATE paper_review_jobs SET state='cancelled',error='学生账号已删除' WHERE state='pending' AND submission_id IN (SELECT id FROM submissions WHERE user_id=?)",(uid,))
            c.execute("UPDATE english_realtime SET state='closed',expires=0 WHERE session_id IN (SELECT id FROM english_sessions WHERE user_id=?)",(uid,))
            c.execute('UPDATE english_sessions SET ended=COALESCE(ended,?) WHERE user_id=?',(time.time(),uid))
            c.execute("UPDATE english_assessments SET status='cancelled',error='学生账号已删除' WHERE status='queued' AND session_id IN (SELECT id FROM english_sessions WHERE user_id=?)",(uid,))
            c.execute('DELETE FROM writing_briefings WHERE assignment_id IN (SELECT assignment_id FROM writing_rounds WHERE user_id=?)',(uid,))
            c.execute('UPDATE writing_rounds SET shared=0 WHERE user_id=?',(uid,))
            c.execute('UPDATE arena_entries SET share_replay=0 WHERE user_id=?',(uid,))
            c.execute("UPDATE arena_entries SET state='cancelled',error='学生账号已删除',lease_hash='',lease_until=0 WHERE user_id=? AND state IN ('waiting','pending','running')",(uid,))
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));c.execute('DELETE FROM practice_pending WHERE user_id=?',(uid,))
            c.execute("UPDATE users SET archived_student_no=student_no,student_no=?,deleted_at=? WHERE id=?",('deleted-'+str(uid)+'-'+secrets.token_hex(6),env['now'](),uid))
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'student-delete',json.dumps({'student':uid,'student_no':x.student_no,'reason':x.reason.strip()},ensure_ascii=False),env['now']()))
        return {'ok':True,'archived':True}


    def recovery_limit(request,no,action):
        env['throttle']('recovery-ip:'+action+':'+request.client.host,60,3600)
        env['throttle']('recovery-account:'+action+':'+hashlib.sha256(no.encode()).hexdigest(),5,3600)

    @app.post('/api/password-recovery/request')
    def recovery_request(x:RecoveryIdentity,request:Request):
        no=x.student_no.strip();phone=phone_value(x.phone)
        recovery_limit(request,no,'request')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            u=c.execute("SELECT * FROM users WHERE student_no=? AND phone=? AND role='student' AND deleted_at=''",(no,phone)).fetchone()
            if u:
                # Repeated public requests never invalidate a still-valid issued code.
                c.execute("DELETE FROM password_recovery WHERE user_id=? AND (expires<? OR password_version<>? OR phone<>?)",(u['id'],time.time(),u['password'],phone))
                c.execute('INSERT OR IGNORE INTO password_recovery(user_id,requested,expires,password_version,phone) VALUES(?,?,?,?,?)',(u['id'],time.time(),time.time()+7*86400,u['password'],phone))
        return {'ok':True,'message':'如学号和电话与登记资料一致，申请已提交。请联系教师核实身份并领取重置码；未登记或更换电话请直接联系教师。'}

    @app.get('/api/teacher/password-recovery')
    def recovery_list(u=Depends(teacher)):
        with db() as c:
            return [dict(r) for r in c.execute("""SELECT u.id,u.name,u.student_no,u.phone,r.requested,r.expires,(r.code_hash<>'') AS issued
                FROM password_recovery r JOIN users u ON u.id=r.user_id
                WHERE u.role='student' AND u.deleted_at='' AND r.expires>? AND r.password_version=u.password AND r.phone=u.phone ORDER BY r.requested DESC""",(time.time(),))]

    @app.post('/api/teacher/password-recovery/{uid}/approve')
    def recovery_approve(uid:int,x:RecoveryApproval,u=Depends(teacher)):
        if not x.verified:raise HTTPException(400,'请先通过登记电话或当面核实学生身份')
        code=secrets.token_hex(6).upper();expires=time.time()+1800
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("""SELECT r.user_id FROM password_recovery r JOIN users u ON u.id=r.user_id
                WHERE u.id=? AND u.role='student' AND u.deleted_at='' AND r.expires>? AND r.password_version=u.password AND r.phone=u.phone""",(uid,time.time())).fetchone()
            if not row:raise HTTPException(404,'申请已过期或账号资料已变更，请学生重新申请')
            c.execute('UPDATE password_recovery SET code_hash=?,expires=? WHERE user_id=?',(hashlib.sha256(code.encode()).hexdigest(),expires,uid))
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'recovery-approve',str(uid),env['now']()))
        return {'code':code,'expires':expires}

    @app.delete('/api/teacher/password-recovery/{uid}')
    def recovery_dismiss(uid:int,u=Depends(teacher)):
        with db() as c:
            c.execute('DELETE FROM password_recovery WHERE user_id=?',(uid,))
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'recovery-dismiss',str(uid),env['now']()))
        return {'ok':True}

    @app.post('/api/password-recovery/reset')
    def recovery_reset(x:RecoveryReset,request:Request):
        no=x.student_no.strip();phone=phone_value(x.phone)
        recovery_limit(request,no,'reset')
        digest=hashlib.sha256(x.code.strip().upper().encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute("""SELECT r.* FROM password_recovery r JOIN users u ON u.id=r.user_id
                WHERE u.student_no=? AND u.phone=? AND u.role='student' AND u.deleted_at=''
                AND r.expires>? AND r.password_version=u.password AND r.phone=u.phone""",(no,phone,time.time())).fetchone()
            if not r or not hmac.compare_digest(r['code_hash'],digest):raise HTTPException(400,'资料或重置码无效、已使用或已过期，请核对或联系教师')
            uid=r['user_id']
            c.execute('UPDATE users SET password=? WHERE id=?',(env['pwdhash'](x.password),uid))
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            c.execute('DELETE FROM password_recovery WHERE user_id=?',(uid,))
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(uid,'password-recovered',str(uid),env['now']()))
        return {'ok':True}
