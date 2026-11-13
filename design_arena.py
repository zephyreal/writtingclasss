"""Authenticated model competition API. Uploaded models are NEVER loaded by this application."""
import io
import csv
import html
import hashlib
import hmac
import json
import math
import secrets
import shutil
import time
import zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Literal
from fastapi import Depends,File,Form,HTTPException,Request,UploadFile
from fastapi.responses import FileResponse,StreamingResponse,JSONResponse
from pydantic import BaseModel,Field,StrictInt
from arena_engine import ENGINE,DEITY_ENGINE,openings,verify_games

BJT=timezone(timedelta(hours=8))
MODEL_LIMIT=20_000_000
SOURCE_LIMIT=5_000_000
ENV={}
ACTIVE=('waiting','pending','running')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS arena_settings(id INTEGER PRIMARY KEY CHECK(id=1),worker_id TEXT NOT NULL DEFAULT 'course-arena-1',token_hash TEXT NOT NULL DEFAULT '',last_seen REAL NOT NULL DEFAULT 0,ready INTEGER NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '尚未连接独立评测机');
    INSERT OR IGNORE INTO arena_settings(id) VALUES(1);
    CREATE TABLE IF NOT EXISTS arena_competitions(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,instructions TEXT NOT NULL,mode TEXT NOT NULL,state TEXT NOT NULL,deadline REAL NOT NULL DEFAULT 0,published INTEGER NOT NULL DEFAULT 0,config TEXT NOT NULL,openings TEXT NOT NULL,baseline_path TEXT NOT NULL,baseline_hash TEXT NOT NULL,fingerprint TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS arena_entries(id INTEGER PRIMARY KEY AUTOINCREMENT,competition_id INTEGER NOT NULL REFERENCES arena_competitions(id),user_id INTEGER NOT NULL REFERENCES users(id),alias TEXT NOT NULL,note TEXT NOT NULL,share_replay INTEGER NOT NULL DEFAULT 0,model_path TEXT NOT NULL,model_name TEXT NOT NULL,model_hash TEXT NOT NULL,source_path TEXT NOT NULL DEFAULT '',source_name TEXT NOT NULL DEFAULT '',state TEXT NOT NULL,error TEXT NOT NULL DEFAULT '',result TEXT,lease_hash TEXT NOT NULL DEFAULT '',lease_until REAL NOT NULL DEFAULT 0,fingerprint TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,created_ts REAL NOT NULL,started REAL,finished REAL);
    CREATE INDEX IF NOT EXISTS arena_pending ON arena_entries(state,id);
    CREATE INDEX IF NOT EXISTS arena_user_versions ON arena_entries(competition_id,user_id,id);
    ''')
    cols={r['name'] for r in c.execute('PRAGMA table_info(arena_entries)')}
    if 'completed_games' not in cols:c.execute('ALTER TABLE arena_entries ADD COLUMN completed_games INTEGER NOT NULL DEFAULT 0')
    if 'phase' not in cols:c.execute("ALTER TABLE arena_entries ADD COLUMN phase TEXT NOT NULL DEFAULT 'queued'")


def deadline_value(value):
    if not value:return 0
    try:
        parsed=datetime.fromisoformat(value)
        if parsed.tzinfo is not None:raise ValueError()
        return parsed.replace(tzinfo=BJT).timestamp()
    except ValueError:raise HTTPException(400,'截止时间请填写北京时间，不带时区后缀')


def audit(c,uid,action,target):c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(uid,'arena-'+action,str(target),ENV['now']()))


def get_comp(c,cid):
    row=c.execute('SELECT * FROM arena_competitions WHERE id=?',(cid,)).fetchone()
    if not row:raise HTTPException(404,'比赛不存在')
    return dict(row)


def release_final(c,cid):
    latest=[r[0] for r in c.execute("SELECT MAX(id) FROM arena_entries WHERE competition_id=? AND state='waiting' GROUP BY user_id",(cid,))]
    for r in c.execute("SELECT id FROM arena_entries WHERE competition_id=? AND state='waiting'",(cid,)).fetchall():
        c.execute('UPDATE arena_entries SET state=? WHERE id=?',('pending' if r['id'] in latest else 'superseded',r['id']))


def maintain(c):
    for r in c.execute("SELECT id,mode FROM arena_competitions WHERE state='open' AND deadline>0 AND deadline<=?",(time.time(),)).fetchall():
        c.execute("UPDATE arena_competitions SET state='closed' WHERE id=?",(r['id'],))
        if r['mode']=='final':release_final(c,r['id'])
    c.execute("UPDATE arena_entries SET state='interrupted',error='评测机连接中断，等待教师重试',lease_hash='',lease_until=0 WHERE state='running' AND lease_until<?",(time.time(),))
    c.execute("UPDATE arena_entries SET state='cancelled',error='账号或课程权限已取消',lease_hash='',lease_until=0 WHERE state IN ('waiting','pending','running') AND user_id NOT IN (SELECT u.id FROM users u JOIN course_memberships m ON m.user_id=u.id WHERE u.deleted_at='' AND m.active=1 AND m.course_id='design')")


def worker_public(c):
    r=c.execute('SELECT * FROM arena_settings WHERE id=1').fetchone()
    return {'configured':bool(r['token_hash']),'worker_id':r['worker_id'],'online':bool(r['ready'] and r['last_seen']>time.time()-75),'last_seen':r['last_seen'],'message':r['last_error'] or '评测机已连接'}


def public_comp(a,teacher=False):
    return {'id':a['id'],'title':a['title'],'instructions':a['instructions'],'mode':a['mode'],'state':a['state'],'published':bool(a['published']),
        'deadline':datetime.fromtimestamp(a['deadline'],BJT).strftime('%Y-%m-%dT%H:%M') if a['deadline'] else '',
        'config':json.loads(a['config']),'baseline_hash':a['baseline_hash'],'fingerprint':a['fingerprint'] if teacher else '', 'created':a['created']}


def can_results(a,u):return u['role']=='teacher' or a['mode']=='practice' or bool(a['published'])


def entry_public(r,a,u):
    visible=can_results(a,u);result=json.loads(r['result']) if r['result'] and visible else None
    if result:result={k:v for k,v in result.items() if k!='replays'}
    return {'id':r['id'],'competition_id':r['competition_id'],'alias':r['alias'],'note':r['note'],'state':r['state'],
        'error':r['error'],'model_name':r['model_name'],'model_hash':r['model_hash'],'source_name':r['source_name'],
        'completed_games':json.loads(a['config'])['pairs']*2 if r['state'] in ('completed','disqualified') else r['completed_games'],
        'total_games':json.loads(a['config'])['pairs']*2,'phase':r['phase'],
        'share_replay':bool(r['share_replay']),'created':r['created'],'result':result,'sealed':not visible and r['state'] in ('completed','disqualified'),
        'fingerprint':r['fingerprint'] if u['role']=='teacher' else '', 'user_id':r['user_id'] if u['role']=='teacher' else None}


class Competition(BaseModel):
    title:str=Field(min_length=2,max_length=120)
    instructions:str=Field(default='',max_length=5000)
    mode:Literal['practice','final']='practice'
    state:Literal['draft','open']='open'
    deadline:str=Field(default='',max_length=40)
    pairs:int=Field(default=20,ge=1,le=50)
    opponent:Literal['shared','deity']='shared'
    simulations:int=Field(default=16,ge=2,le=150)
    move_ms:int=Field(default=2000,ge=100,le=10000)
    job_seconds:int=Field(default=1800,ge=60,le=7200)
    daily_limit:int=Field(default=2,ge=1,le=10)

class CompetitionEdit(BaseModel):
    title:str|None=Field(default=None,min_length=2,max_length=120)
    instructions:str|None=Field(default=None,max_length=5000)
    deadline:str|None=Field(default=None,max_length=40)
    state:Literal['open','closed']|None=None
    published:bool|None=None

class WorkerSetup(BaseModel):worker_id:str=Field(default='course-arena-1',pattern='^[A-Za-z0-9_-]{3,60}$')
class WorkerInfo(BaseModel):
    worker_id:str=Field(max_length=60)
    fingerprint:str=Field(pattern='^[0-9a-f]{64}$')
    engines:list[Literal[ENGINE,DEITY_ENGINE]]=Field(default_factory=lambda:[ENGINE],max_length=2)
    deity_sha:str=Field(default='',pattern='^([0-9a-f]{64})?$')
    ready:bool=True
    error:str=Field(default='',max_length=200)
class Lease(BaseModel):lease:str=Field(min_length=20,max_length=100)
class Claim(WorkerInfo):
    function_v1:bool=False
class Heartbeat(Lease):
    completed_games:StrictInt|None=Field(default=None,ge=0,le=100)
    phase:Literal['validating','playing']|None=None
class Game(BaseModel):
    index:StrictInt=Field(ge=0,le=99)
    student_color:Literal[-1,1]
    moves:list[StrictInt]=Field(max_length=225)
    times_ms:list[float]=Field(default_factory=list,max_length=225)
    fault:Literal['','student_timeout','student_error','student_illegal']=''
class Result(Lease):
    fingerprint:str=Field(pattern='^[0-9a-f]{64}$')
    status:Literal['completed','rejected','failed']
    error:str=Field(default='',max_length=500)
    games:list[Game]=Field(default_factory=list,max_length=100)
class Reason(BaseModel):reason:str=Field(min_length=2,max_length=500)
class Sharing(BaseModel):share_replay:bool


class WorkerPayloadLimit:
    """Bound worker JSON before FastAPI parses it; multipart student uploads use their own limits."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not scope.get('path','').startswith('/api/arena/worker/') or scope.get('method')!='POST':
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]))
        if headers.get(b'content-type',b'').split(b';')[0].strip()!=b'application/json':
            return await JSONResponse({'detail':'评测机请求须使用JSON'},415)(scope,receive,send)
        body=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            body.extend(message.get('body',b''))
            if len(body)>2_000_000:return await JSONResponse({'detail':'评测报告超过2MB上限'},413)(scope,receive,send)
            if not message.get('more_body',False):break
        used=False
        async def replay():
            nonlocal used
            if not used:
                used=True;return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)


def _finish_zip(z, output):
    z.close()
    return output.getvalue()

def register(app,env):
    global ENV
    ENV=env;db=lambda:env['db']();current=env['current'];teacher=env['teacher']
    app.add_middleware(WorkerPayloadLimit)

    def worker(request:Request):
        authorization=request.headers.get('authorization','')
        token=authorization[7:] if authorization.startswith('Bearer ') else ''
        with db() as c:expected=c.execute('SELECT token_hash FROM arena_settings WHERE id=1').fetchone()[0]
        if not expected or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),expected):raise HTTPException(401,'评测机凭证无效')
        return True

    def leased(c,eid,token):
        maintain(c);r=c.execute('SELECT * FROM arena_entries WHERE id=?',(eid,)).fetchone()
        if not r or r['state']!='running' or r['lease_until']<=time.time() or not hmac.compare_digest(r['lease_hash'],hashlib.sha256(token.encode()).hexdigest()):raise HTTPException(409,'任务已取消或租约已过期')
        return r

    @app.get('/api/arena/competitions')
    def competitions(u=Depends(current)):
        with db() as c:
            maintain(c);rows=c.execute('SELECT * FROM arena_competitions ORDER BY id DESC').fetchall()
            return {'competitions':[public_comp(dict(r),u['role']=='teacher') for r in rows if u['role']=='teacher' or r['state']!='draft'],'worker':worker_public(c)}

    @app.post('/api/arena/admin/competitions')
    def create(x:Competition,u=Depends(teacher)):
        if not x.title.strip():raise HTTPException(400,'请填写比赛名称')
        if x.opponent=='deity' and (x.simulations!=150 or x.move_ms<2000):raise HTTPException(400,'化神挑战赛学生固定150次搜索，每步时限至少2000毫秒')
        due=deadline_value(x.deadline)
        if x.mode=='final' and (not due or due<=time.time()):raise HTTPException(400,'结课赛须设置将来的截止时间')
        source=Path(env['ROOT'])/'course_assets/gomoku/gomoku_uint8_qop_u8u8.onnx'
        if not source.is_file():raise HTTPException(503,'教师基准模型未安装，请完成网站升级')
        folder=Path(env['DATA'])/'arena-baselines';folder.mkdir(exist_ok=True,mode=0o700)
        path=folder/(secrets.token_hex(16)+'.onnx');shutil.copyfile(source,path)
        try:
            config={'submission':'function-v1','engine':DEITY_ENGINE if x.opponent=='deity' else ENGINE,'pairs':x.pairs,'simulations':x.simulations,'move_ms':x.move_ms,'job_seconds':x.job_seconds,'daily_limit':x.daily_limit,'memory_mb':1024,'threads':1}
            if x.opponent=='deity':config['deity_sha']=hashlib.sha256((Path(env['ROOT'])/'course_assets/gomoku/ai-worker.js').read_bytes()).hexdigest()
            bank=openings(secrets.token_hex(24),x.pairs)
            with db() as c:
                cid=c.execute('INSERT INTO arena_competitions(title,instructions,mode,state,deadline,published,config,openings,baseline_path,baseline_hash,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (x.title.strip(),x.instructions.strip(),x.mode,x.state,due,int(x.mode=='practice'),json.dumps(config),json.dumps(bank),str(path),hashlib.sha256(path.read_bytes()).hexdigest(),env['now']())).lastrowid
                audit(c,u['id'],'create',cid)
        except Exception:path.unlink(missing_ok=True);raise
        return {'ok':True,'id':cid}

    @app.put('/api/arena/admin/competitions/{cid}')
    def edit(cid:int,x:CompetitionEdit,u=Depends(teacher)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');maintain(c);a=get_comp(c,cid)
            if x.state=='open' and a['state']=='closed':raise HTTPException(409,'已封存比赛不可重新开放，请另建比赛以保持赛制一致')
            if x.deadline is not None and a['state']=='closed':raise HTTPException(409,'已结束比赛不能修改截止时间')
            if x.title is not None:
                if not x.title.strip():raise HTTPException(400,'比赛名称不能为空')
                c.execute('UPDATE arena_competitions SET title=? WHERE id=?',(x.title.strip(),cid))
            if x.instructions is not None:c.execute('UPDATE arena_competitions SET instructions=? WHERE id=?',(x.instructions.strip(),cid))
            if x.deadline is not None:
                due=deadline_value(x.deadline)
                if a['mode']=='final' and (not due or due<=time.time()):raise HTTPException(400,'结课赛截止时间须在将来；立即结束请点击封存')
                c.execute('UPDATE arena_competitions SET deadline=? WHERE id=?',(due,cid))
            if x.state:
                c.execute('UPDATE arena_competitions SET state=? WHERE id=?',(x.state,cid))
                if x.state=='closed' and a['mode']=='final':release_final(c,cid)
            if x.published is not None:
                state=x.state or a['state']
                if x.published and a['mode']=='final':
                    if state!='closed' or c.execute("SELECT 1 FROM arena_entries WHERE competition_id=? AND state IN ('waiting','pending','running')",(cid,)).fetchone():raise HTTPException(409,'先封存并完成所有待评测任务，再发布结课赛成绩')
                c.execute('UPDATE arena_competitions SET published=? WHERE id=?',(int(x.published),cid))
            audit(c,u['id'],'edit',cid)
        return {'ok':True}

    @app.post('/api/arena/admin/worker')
    def configure(x:WorkerSetup,u=Depends(teacher)):
        token=secrets.token_urlsafe(40)
        with db() as c:
            c.execute("UPDATE arena_settings SET worker_id=?,token_hash=?,ready=0,last_seen=0,last_error='等待评测机连接' WHERE id=1",(x.worker_id,hashlib.sha256(token.encode()).hexdigest()))
            c.execute("UPDATE arena_entries SET state='interrupted',error='教师已更新评测机凭证，请重试',lease_hash='',lease_until=0 WHERE state='running'")
            audit(c,u['id'],'worker-key-rotated',x.worker_id)
        return {'token':token,'worker_id':x.worker_id}

    @app.get('/api/arena/competitions/{cid}/baseline')
    def baseline(cid:int,u=Depends(current)):
        with db() as c:a=get_comp(c,cid)
        if a['state']=='draft' and u['role']!='teacher':raise HTTPException(404,'比赛尚未发布')
        return FileResponse(a['baseline_path'],filename='teacher-baseline.onnx')

    @app.get('/api/arena/competitions/{cid}/starter')
    def starter(cid:int,u=Depends(current)):
        with db() as c:a=get_comp(c,cid)
        if a['state']=='draft' and u['role']!='teacher':raise HTTPException(404,'比赛尚未发布')
        output=io.BytesIO();root=Path(env['ROOT'])
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            if json.loads(a['config']).get('submission')=='function-v1':
                for name in ('agent.py','function_agent.py','local_function_test.py','START.bat','FUNCTION.md'):
                    z.writestr(name,(root/'arena'/name).read_bytes())
                z.writestr('arena_engine.py',(root/'arena_engine.py').read_bytes())
                z.writestr('competition.json',json.dumps(public_comp(a),ensure_ascii=False,indent=2))
                return StreamingResponse(iter([_finish_zip(z,output)]),media_type='application/zip',headers={'Content-Disposition':'attachment; filename=gomoku-function-starter.zip'})
            for name in ('arena_engine.py','arena/runner.py','arena/example_model.py','arena/train_example.py','arena/local_check.py','arena/requirements.txt','arena/STUDENT.md','arena/student_workflow.py','arena/training_config.json'):
                path=root/name
                if not path.is_file():raise HTTPException(503,'入门模板未安装，请完成本次网站升级')
                z.writestr(name,path.read_bytes())
            for name in ('01_setup.bat','02_train.bat','03_check.bat'):
                z.writestr(name,(root/'arena'/name).read_bytes())
            z.writestr('arena/__init__.py','')
            z.writestr('README.md',(root/'arena/STUDENT.md').read_bytes())
            z.writestr('teacher-baseline.onnx',Path(a['baseline_path']).read_bytes())
            z.writestr('competition.json',json.dumps(public_comp(a),ensure_ascii=False,indent=2))
        return StreamingResponse(iter([output.getvalue()]),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="gomoku-model-starter.zip"'})

    @app.post('/api/arena/competitions/{cid}/entries')
    async def submit(cid:int,model:UploadFile=File(...),alias:str=Form(''),note:str=Form(''),share_replay:bool=Form(False),source:UploadFile|None=File(None),u=Depends(current)):
        if u['role']!='student':raise HTTPException(403,'请使用学生账号参赛')
        alias=alias.strip() or ('同学'+str(u['id']))
        if not 1<=len(alias.strip())<=30 or len(note)>2000:raise HTTPException(400,'请填写1—30字参赛昵称，改进说明不超过2000字')
        env['throttle']('arena-upload:'+str(u['id']),12,3600)
        def check(c):
            maintain(c);a=get_comp(c,cid)
            if a['state']!='open':raise HTTPException(409,'比赛尚未开放或已经封存')
            midnight=datetime.now(BJT).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            cfg=json.loads(a['config'])
            if c.execute('SELECT COUNT(*) FROM arena_entries WHERE competition_id=? AND user_id=? AND created_ts>=?',(cid,u['id'],midnight)).fetchone()[0]>=cfg['daily_limit']:raise HTTPException(429,'今天的参赛提交次数已用完，教师可重试基础设施失败的任务')
            if c.execute("SELECT COUNT(*) FROM arena_entries WHERE state IN ('waiting','pending','running')").fetchone()[0]>=1000:raise HTTPException(429,'评测队列已满，请稍后提交')
            return a
        with db() as c:a=check(c)
        is_function=json.loads(a['config']).get('submission')=='function-v1'
        if is_function:
            if source and source.filename:raise HTTPException(400,'只上传agent.py，不接受工程文件')
            if (model.filename or '').lower()!='agent.py':raise HTTPException(400,'请上传单个agent.py文件')
            import ast
            content=await model.read(900001)
            if not content or len(content)>900000:raise HTTPException(400,'代码须小于900KB')
            try:
                tree=ast.parse(content.decode('utf-8-sig'))
                functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='choose_move']
                if len(functions)!=1:raise ValueError()
                args=functions[0].args
                if len(args.posonlyargs)+len(args.args)!=1 or args.kwonlyargs or args.vararg or args.kwarg:raise ValueError()
            except (ValueError,SyntaxError,UnicodeError):raise HTTPException(400,'请定义choose_move(board)函数，并检查UTF-8编码和Python语法')
            await model.seek(0)
        path,name=await env['save_upload'](model,{'.py'} if is_function else {'.onnx'},900000 if is_function else MODEL_LIMIT);source_path=source_name=''
        try:
            if source and source.filename:
                source_path,source_name=await env['save_upload'](source,{'.zip'},SOURCE_LIMIT)
                try:
                    with zipfile.ZipFile(source_path) as z:
                        items=z.infolist()
                        if len(items)>200 or sum(i.file_size for i in items)>30_000_000:raise ValueError()
                        for i in items:
                            name_parts=Path(i.filename.replace('\\','/'))
                            if name_parts.is_absolute() or '..' in name_parts.parts or ':' in i.filename or i.flag_bits&1 or ((i.external_attr>>16)&0o170000)==0o120000:raise ValueError()
                except Exception:raise HTTPException(400,'源代码ZIP无效、含危险路径、加密内容或解压体积过大')
            with db() as c:
                c.execute('BEGIN IMMEDIATE');a=check(c)
                eid=c.execute('INSERT INTO arena_entries(competition_id,user_id,alias,note,share_replay,model_path,model_name,model_hash,source_path,source_name,state,created,created_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (cid,u['id'],alias.strip(),note.strip(),int(share_replay),path,name,hashlib.sha256(Path(path).read_bytes()).hexdigest(),source_path,source_name,'waiting' if a['mode']=='final' else 'pending',env['now'](),time.time())).lastrowid
                audit(c,u['id'],'submit',eid)
        except Exception:
            Path(path).unlink(missing_ok=True)
            if source_path:Path(source_path).unlink(missing_ok=True)
            raise
        return {'ok':True,'id':eid,'state':'waiting' if a['mode']=='final' else 'pending'}

    @app.get('/api/arena/competitions/{cid}/entries')
    def entries(cid:int,u=Depends(current)):
        with db() as c:
            maintain(c);a=get_comp(c,cid)
            if a['state']=='draft' and u['role']!='teacher':raise HTTPException(404,'比赛尚未发布')
            query='SELECT e.*,u.name,u.student_no FROM arena_entries e JOIN users u ON u.id=e.user_id WHERE e.competition_id=?';args=[cid]
            if u['role']!='teacher':query+=' AND e.user_id=?';args.append(u['id'])
            rows=c.execute(query+' ORDER BY e.id DESC',args).fetchall()
            result=[]
            for r in rows:
                item=entry_public(r,a,u)
                if u['role']=='teacher':item.update(name=r['name'],student_no=r['student_no'])
                result.append(item)
            quota=None
            if u['role']=='student':
                midnight=datetime.now(BJT).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
                used=c.execute('SELECT COUNT(*) FROM arena_entries WHERE competition_id=? AND user_id=? AND created_ts>=?',(cid,u['id'],midnight)).fetchone()[0]
                limit=json.loads(a['config'])['daily_limit']
                quota={'used':used,'limit':limit,'remaining':max(0,limit-used),'timezone':'Asia/Shanghai'}
            return {'competition':public_comp(a,u['role']=='teacher'),'entries':result,'worker':worker_public(c),'quota':quota}

    @app.get('/api/arena/competitions/{cid}/leaderboard')
    def leaderboard(cid:int,u=Depends(current)):
        with db() as c:
            maintain(c);a=get_comp(c,cid)
            if a['state']=='draft' and u['role']!='teacher':raise HTTPException(404,'比赛尚未发布')
            if not a['published'] and u['role']!='teacher':return {'sealed':True,'rows':[]}
            rows=c.execute("SELECT e.*,u.name,u.student_no FROM arena_entries e JOIN users u ON u.id=e.user_id JOIN course_memberships m ON m.user_id=u.id AND m.course_id='design' AND m.active=1 WHERE e.competition_id=? AND u.deleted_at='' AND e.id IN (SELECT MAX(id) FROM arena_entries WHERE competition_id=? AND state IN ('completed','disqualified') GROUP BY user_id)",(cid,cid)).fetchall()
            items=[]
            for r in rows:
                if r['state']!='completed':continue
                res=json.loads(r['result']);item={'entry_id':r['id'],'alias':r['alias'],'created':r['created'],'score':res['score'],'wins':res['wins'],'draws':res['draws'],'losses':res['losses'],'games':res['games'],'mean_move_ms':res['mean_move_ms'],'can_replay':bool(r['share_replay'] or r['user_id']==u['id'] or u['role']=='teacher')}
                if u['role']=='teacher':item.update(name=r['name'],student_no=r['student_no'])
                items.append(item)
            items.sort(key=lambda x:(-x['score'],x['entry_id']));previous=None;rank=0
            for n,r in enumerate(items,1):
                if previous!=r['score']:rank=n
                r['rank']=rank;previous=r['score']
            return {'sealed':False,'rows':items}

    @app.get('/api/arena/admin/competitions/{cid}/export')
    def export_records(cid:int,u=Depends(teacher)):
        ranking=leaderboard(cid,u);ranks={r['entry_id']:r['rank'] for r in ranking['rows']}
        with db() as c:
            maintain(c);a=get_comp(c,cid)
            rows=c.execute('SELECT e.*,u.name,u.student_no FROM arena_entries e JOIN users u ON u.id=e.user_id WHERE e.competition_id=? ORDER BY e.id DESC',(cid,)).fetchall()
            audit(c,u['id'],'export-records',cid)
        output=io.StringIO();writer=csv.writer(output)
        writer.writerow(['比赛','版本','姓名','学号','参赛昵称','状态','当前排名','比赛分','胜','平','负','对局数','模型SHA256','提交时间','改进说明','异常说明'])
        def safe(value):
            value=str(value if value is not None else '')
            return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value
        for r in rows:
            result=json.loads(r['result']) if r['result'] else {}
            writer.writerow([safe(x) for x in [a['title'],r['id'],r['name'],r['student_no'],r['alias'],r['state'],ranks.get(r['id'],''),result.get('score',''),result.get('wins',''),result.get('draws',''),result.get('losses',''),result.get('games',''),r['model_hash'],r['created'],r['note'],r['error']]])
        return StreamingResponse(iter([output.getvalue().encode('utf-8-sig')]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="arena-{cid}-records.csv"','Cache-Control':'no-store'})

    @app.get('/api/arena/entries/{eid}/report')
    def report(eid:int,format:Literal['html','json']='html',u=Depends(current)):
        with db() as c:
            maintain(c);r=c.execute('SELECT * FROM arena_entries WHERE id=?',(eid,)).fetchone()
            if not r or (u['role']!='teacher' and r['user_id']!=u['id']):raise HTTPException(404,'参赛记录不存在')
            a=get_comp(c,r['competition_id'])
            if not can_results(a,u):raise HTTPException(403,'结课赛报告在教师发布后开放')
            if r['state'] not in ('completed','disqualified') or not r['result']:raise HTTPException(409,'完整评测结束后才能下载报告')
            result=json.loads(r['result']);colors=[]
            for color,label in ((1,'执黑'),(-1,'执白')):
                games=[g for g in result['replays'] if g['student_color']==color]
                wins=sum(g['winner']==color for g in games);draws=sum(g['winner']==0 for g in games)
                colors.append({'label':label,'games':len(games),'wins':wins,'draws':draws,'losses':len(games)-wins-draws,'faults':sum(bool(g.get('fault')) for g in games)})
            payload={'schema':'arena-report-v1','competition':public_comp(a),'entry':entry_public(r,a,u),'colors':colors,'replays':result['replays'],'engine':json.loads(a['config'])['engine'],'fingerprint':r['fingerprint'],'exported_at':env['now']()}
            audit(c,u['id'],'download-report',eid)
        if format=='json':
            content=json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8');media='application/json'
        else:
            esc=lambda v:html.escape(str(v if v is not None else ''))
            rows=''.join('<tr>'+''.join('<td>'+esc(item[key])+'</td>' for key in ('label','games','wins','draws','losses','faults'))+'</tr>' for item in colors)
            cfg=payload['competition']['config']
            rules=('教师：冻结化神引擎（严格VCF＋50/100/150自适应MCTS）；学生：统一150次MCTS。双方每步相同时限。' if cfg['engine']==DEITY_ENGINE else '双方相同固定MCTS搜索预算。')
            content=(f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>模型评测报告 #{eid}</title>'
                '<style>body{max-width:880px;margin:36px auto;padding:0 20px;font:16px/1.7 system-ui;color:#20334b}h1{font-size:26px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d7e0eb;padding:8px;text-align:left}code{overflow-wrap:anywhere}p{white-space:pre-wrap}.note{padding:12px;background:#eef3f9}@media print{body{margin:0}}</style>'
                f'<h1>{esc(a["title"])} · 版本 #{eid}</h1><p>参赛昵称：{esc(r["alias"])}\n提交时间：{esc(r["created"])}\n记录状态：{esc(r["state"])}</p>'
                +('<p class="note">本版成绩已撤销，不计入排行榜；本报告仅为历史记录。</p>' if r['state']=='disqualified' else '')
                +f'<h2>比赛分：{esc(result["score"])} / 100</h2><p>{result["wins"]}胜 / {result["draws"]}平 / {result["losses"]}负，共{result["games"]}局。胜100、平50、负0，取全部对局平均。比赛分不等于课程总评。</p>'
                f'<table><tr><th>执棋</th><th>局数</th><th>胜</th><th>平</th><th>负</th><th>异常判负局</th></tr>{rows}</table>'
                f'<h2>评测标准</h2><p>15×15，无禁手，连五及以上获胜。{esc(rules)}\n学生策略：{"自主落子函数" if cfg.get("submission")=="function-v1" else str(cfg["simulations"])+"次搜索"}，每步上限{cfg["move_ms"]}毫秒；整次上限{cfg["job_seconds"]}秒。\n引擎：{esc(cfg["engine"])}</p>'
                f'<p>化神代码 SHA-256：<code>{esc(cfg.get("deity_sha","不适用"))}</code></p>'
                f'<p>本版模型 SHA-256：<code>{esc(r["model_hash"])}</code></p><p>教师基准 SHA-256：<code>{esc(a["baseline_hash"])}</code></p><p>评测环境指纹：<code>{esc(r["fingerprint"])}</code></p>'
                f'<h2>本版改进说明</h2><p>{esc(r["note"] or "未填写")}</p><p class="note">对局数量有限，小分差不代表能力必然领先。异常判负已计入对应负局。完整棋谱可在网页复盘，或下载JSON报告留档。</p><p>导出时间：{esc(payload["exported_at"])}</p></html>').encode('utf-8');media='text/html'
        return StreamingResponse(iter([content]),media_type=media,headers={'Content-Disposition':f'attachment; filename="arena-entry-{eid}.{format}"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; sandbox"})

    @app.get('/api/arena/entries/{eid}/replay')
    def replay(eid:int,u=Depends(current)):
        with db() as c:
            r=c.execute('SELECT * FROM arena_entries WHERE id=?',(eid,)).fetchone()
            if not r:raise HTTPException(404,'参赛记录不存在')
            a=get_comp(c,r['competition_id'])
            if not can_results(a,u):raise HTTPException(403,'结课赛棋谱在教师发布后开放')
            if u['role']!='teacher' and r['user_id']!=u['id'] and not c.execute("SELECT 1 FROM users u JOIN course_memberships m ON m.user_id=u.id AND m.course_id='design' AND m.active=1 WHERE u.id=? AND u.deleted_at=''",(r['user_id'],)).fetchone():raise HTTPException(403,'该参赛者已不在本课程公开棋谱')
            if u['role']!='teacher' and r['user_id']!=u['id'] and (not r['share_replay'] or not a['published'] or r['state']!='completed'):raise HTTPException(403,'该参赛者未开放棋谱')
            if r['state'] not in ('completed','disqualified') or not r['result']:raise HTTPException(409,'尚无完整有效棋谱')
            res=json.loads(r['result']);return {'entry':entry_public(r,a,u),'games':res['replays']}

    @app.get('/api/arena/entries/{eid}/files/{kind}')
    def artifact(eid:int,kind:Literal['model','source'],u=Depends(current)):
        with db() as c:r=c.execute('SELECT * FROM arena_entries WHERE id=?',(eid,)).fetchone()
        if not r or (u['role']!='teacher' and r['user_id']!=u['id']):raise HTTPException(404,'文件不存在')
        path=r[kind+'_path'];name=r[kind+'_name']
        if not path or not Path(path).is_file():raise HTTPException(404,'文件未上传或已缺失')
        return FileResponse(path,filename=name)

    @app.put('/api/arena/entries/{eid}/sharing')
    def sharing(eid:int,x:Sharing,u=Depends(current)):
        with db() as c:
            if not c.execute('SELECT 1 FROM arena_entries WHERE id=? AND user_id=?',(eid,u['id'])).fetchone():raise HTTPException(404,'参赛记录不存在')
            c.execute('UPDATE arena_entries SET share_replay=? WHERE id=?',(int(x.share_replay),eid));audit(c,u['id'],'sharing',str(eid)+'/'+str(x.share_replay))
        return {'ok':True}

    @app.post('/api/arena/entries/{eid}/withdraw')
    def withdraw(eid:int,u=Depends(current)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM arena_entries WHERE id=?',(eid,)).fetchone()
            if not r or r['user_id']!=u['id']:raise HTTPException(404,'参赛记录不存在')
            if r['state'] not in ('waiting','pending','rejected','failed','interrupted'):raise HTTPException(409,'运行中或已出成绩的版本不能自行撤回')
            c.execute("UPDATE arena_entries SET state='withdrawn',lease_hash='',lease_until=0 WHERE id=?",(eid,));audit(c,u['id'],'withdraw',eid)
        return {'ok':True}

    @app.post('/api/arena/admin/entries/{eid}/retry')
    def retry(eid:int,x:Reason,u=Depends(teacher)):
        if not x.reason.strip():raise HTTPException(400,'请填写重试原因')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');maintain(c);r=c.execute('SELECT * FROM arena_entries WHERE id=?',(eid,)).fetchone()
            if not r:raise HTTPException(404,'记录不存在')
            a=get_comp(c,r['competition_id'])
            if r['state'] not in ('failed','interrupted'):raise HTTPException(409,'仅可重试评测基础设施失败的任务，模型不合格请由学生修改重交')
            if a['mode']=='final' and a['published']:raise HTTPException(409,'请先撤回结课赛成绩发布再重试')
            c.execute("UPDATE arena_entries SET state='pending',error='',result=NULL,lease_hash='',lease_until=0,completed_games=0,phase='queued' WHERE id=?",(eid,));audit(c,u['id'],'retry',json.dumps({'entry':eid,'reason':x.reason},ensure_ascii=False))
        return {'ok':True}

    @app.post('/api/arena/admin/entries/{eid}/exclude')
    def exclude(eid:int,x:Reason,u=Depends(teacher)):
        if not x.reason.strip():raise HTTPException(400,'请填写撤销原因')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT state FROM arena_entries WHERE id=?',(eid,)).fetchone()
            if not r or r['state']!='completed':raise HTTPException(409,'仅能撤销已完成的成绩')
            c.execute("UPDATE arena_entries SET state='disqualified',error=? WHERE id=?",(x.reason,eid));audit(c,u['id'],'exclude',json.dumps({'entry':eid,'reason':x.reason},ensure_ascii=False))
        return {'ok':True}

    @app.post('/api/arena/worker/ping')
    def ping(x:WorkerInfo,auth=Depends(worker)):
        with db() as c:
            if c.execute('SELECT worker_id FROM arena_settings WHERE id=1').fetchone()[0]!=x.worker_id:raise HTTPException(403,'评测机标识不匹配')
            c.execute('UPDATE arena_settings SET last_seen=?,ready=?,last_error=? WHERE id=1',(time.time(),int(x.ready),x.error))
        return {'ok':True}

    @app.post('/api/arena/worker/claim')
    def claim(x:Claim,auth=Depends(worker)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');maintain(c);settings=c.execute('SELECT * FROM arena_settings WHERE id=1').fetchone()
            if x.worker_id!=settings['worker_id'] or not x.ready:raise HTTPException(403,'评测机尚未就绪或标识不匹配')
            c.execute("UPDATE arena_settings SET last_seen=?,ready=1,last_error='' WHERE id=1",(time.time(),))
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vehicle_entries'").fetchone():
                if c.execute("SELECT 1 FROM vehicle_entries WHERE state='running' AND lease_until>?",(time.time(),)).fetchone():return {'job':None}
            if c.execute("SELECT 1 FROM arena_entries WHERE state='running'").fetchone():return {'job':None}
            rows=c.execute("SELECT e.* FROM arena_entries e JOIN arena_competitions a ON a.id=e.competition_id WHERE e.state='pending' AND (a.mode='practice' OR a.state='closed') ORDER BY COALESCE((SELECT MAX(h.started) FROM arena_entries h WHERE h.user_id=e.user_id),0), e.id").fetchall()
            r=None;a=None
            for candidate in rows:
                comp=get_comp(c,candidate['competition_id'])
                cfg=json.loads(comp['config'])
                if cfg.get('submission')=='function-v1' and not x.function_v1:continue
                if cfg['engine'] not in x.engines:continue
                if cfg['engine']==DEITY_ENGINE and cfg.get('deity_sha')!=x.deity_sha:continue
                if comp['fingerprint'] and comp['fingerprint']!=x.fingerprint:continue
                r=candidate;a=comp;break
            if r is None:
                if rows:c.execute("UPDATE arena_settings SET ready=0,last_error='待评比赛的引擎版本、镜像或CPU与评测机不匹配，请升级或恢复对应环境' WHERE id=1")
                return {'job':None}
            if not a['fingerprint']:c.execute('UPDATE arena_competitions SET fingerprint=? WHERE id=?',(x.fingerprint,a['id']))
            lease=secrets.token_urlsafe(32)
            c.execute("UPDATE arena_entries SET state='running',lease_hash=?,lease_until=?,started=?,fingerprint=?,error='',completed_games=0,phase='validating' WHERE id=?",(hashlib.sha256(lease.encode()).hexdigest(),time.time()+90,time.time(),x.fingerprint,r['id']))
            return {'job':{'id':r['id'],'competition_id':a['id'],'lease':lease,'config':json.loads(a['config']),'openings':json.loads(a['openings']),'model_hash':r['model_hash'],'baseline_hash':a['baseline_hash'],'fingerprint':x.fingerprint}}

    @app.post('/api/arena/worker/jobs/{eid}/heartbeat')
    def heartbeat(eid:int,x:Heartbeat,auth=Depends(worker)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');r=leased(c,eid,x.lease)
            cfg=json.loads(get_comp(c,r['competition_id'])['config'])
            if x.completed_games is not None:
                if x.completed_games<r['completed_games'] or x.completed_games>cfg['pairs']*2:raise HTTPException(400,'对局进度不得倒退或超过本次赛制')
                c.execute('UPDATE arena_entries SET completed_games=? WHERE id=?',(x.completed_games,eid))
            if x.phase is not None:
                if r['phase']=='playing' and x.phase=='validating':raise HTTPException(400,'模型检查完成后不能退回检查阶段')
                c.execute('UPDATE arena_entries SET phase=? WHERE id=?',(x.phase,eid))
            c.execute('UPDATE arena_entries SET lease_until=? WHERE id=?',(time.time()+90,eid));c.execute('UPDATE arena_settings SET last_seen=?,ready=1 WHERE id=1',(time.time(),))
        return {'ok':True}

    @app.get('/api/arena/worker/jobs/{eid}/files/{kind}')
    def worker_file(eid:int,kind:Literal['model','baseline'],request:Request,auth=Depends(worker)):
        with db() as c:
            r=leased(c,eid,request.headers.get('X-Arena-Lease',''));a=get_comp(c,r['competition_id'])
            path=r['model_path'] if kind=='model' else a['baseline_path']
        return FileResponse(path,filename=kind+'.onnx')

    @app.post('/api/arena/worker/jobs/{eid}/result')
    def result(eid:int,x:Result,auth=Depends(worker)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');r=leased(c,eid,x.lease);a=get_comp(c,r['competition_id'])
            if x.fingerprint!=r['fingerprint'] or x.fingerprint!=a['fingerprint']:raise HTTPException(409,'评测环境与比赛冻结版本不一致')
            report=None
            if x.status=='completed':
                try:report=verify_games(json.loads(a['openings']),[g.model_dump() for g in x.games],json.loads(a['config'])['move_ms'])
                except (ValueError,KeyError,TypeError,ArithmeticError) as exc:raise HTTPException(400,str(exc))
            elif not x.error.strip():raise HTTPException(400,'未完成评测须说明原因')
            c.execute("UPDATE arena_entries SET state=?,error=?,result=?,lease_hash='',lease_until=0,finished=? WHERE id=?",(x.status,x.error if x.status!='completed' else '',json.dumps(report) if report else None,time.time(),eid))
            if x.status=='completed':c.execute("UPDATE arena_entries SET completed_games=?,phase='finished' WHERE id=?",(len(x.games),eid))
            audit(c,None,'worker-result',json.dumps({'entry':eid,'state':x.status,'fingerprint':x.fingerprint}))
        return {'ok':True}
