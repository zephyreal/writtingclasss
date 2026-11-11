"""Course worklist, grounded document reader, explicit batch grading and portfolios."""
import hashlib
import html
import io
import json
import math
import re
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Literal
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import writing_scores

DEFAULT_RUBRICS = [
    [{'name':'研究问题与意义','max':30},{'name':'文献比较与选题依据','max':30},{'name':'证据来源与研究路线','max':25},{'name':'提纲与表达规范','max':15}],
    [{'name':'初稿结构与论证路线','max':25},{'name':'论点与证据对应','max':35},{'name':'图表与正文关联','max':20},{'name':'引用与表达规范','max':20}],
    [{'name':'关键问题修改质量','max':40},{'name':'修改理由与建议取舍','max':25},{'name':'论证与图表一致性','max':20},{'name':'遗留问题与规范','max':15}],
    [{'name':'终稿完整性与逻辑','max':30},{'name':'证据与图表支撑','max':25},{'name':'修改成果与反馈回应','max':25},{'name':'引用规范与AI使用说明','max':20}],
]
PREVIEW_SLOT = threading.Lock()
ENV = {}

def migrate(c):
    if 'stage_rubrics' not in {r['name'] for r in c.execute('PRAGMA table_info(assignments)')}:
        c.execute("ALTER TABLE assignments ADD COLUMN stage_rubrics TEXT NOT NULL DEFAULT '[]'")
    if 'source_json' not in {r['name'] for r in c.execute('PRAGMA table_info(writing_rounds)')}:
        c.execute('ALTER TABLE writing_rounds ADD COLUMN source_json TEXT')
    if 'graded_policy' not in {r['name'] for r in c.execute('PRAGMA table_info(writing_rounds)')}:c.execute("ALTER TABLE writing_rounds ADD COLUMN graded_policy TEXT NOT NULL DEFAULT ''")
    if 'graded_revision' not in {r['name'] for r in c.execute('PRAGMA table_info(writing_rounds)')}:c.execute('ALTER TABLE writing_rounds ADD COLUMN graded_revision INTEGER')

def validate_rubrics(value):
    if value==[]:return []
    if not isinstance(value,list) or len(value)!=4:raise HTTPException(400,'分轮标准须完整填写四轮，或全部留空沿用通用量规')
    for rubric in value:
        if not isinstance(rubric,list) or not 1<=len(rubric)<=10:raise HTTPException(400,'每轮须有1—10个评分维度')
        names=[]
        for r in rubric:
            name=r.get('name','').strip();score=r.get('max')
            if not name or len(name)>80 or type(score) not in (int,float) or not math.isfinite(score) or not 0<score<=100:raise HTTPException(400,'评分维度名称或分值无效')
            r['name']=name;names.append(name)
        if len(set(names))!=len(names) or abs(sum(r['max'] for r in rubric)-100)>.001:raise HTTPException(400,'每轮评分维度不可重复，且须合计100分')
    return value

def rubric_for(a,number):
    value=a.get('stage_rubrics',[])
    if isinstance(value,str):value=json.loads(value)
    return value[number-1] if value else json.loads(a['rubric']) if isinstance(a['rubric'],str) else a['rubric']

def policy_hash(a,number):
    policy={k:a.get(k,'') for k in ('title','instructions','grading_instructions')}
    policy['rubric']=[{'name':r['name'].strip(),'max':float(r['max'])} for r in rubric_for(a,number)]
    return hashlib.sha256(json.dumps(policy,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def grade_current(row,a):
    expected=policy_hash(a,row['round_no'])
    if row['graded_policy']:return row['graded_policy']==expected
    return row['graded_revision']==a['revision'] or policy_hash(json.loads(row['assignment_snapshot']),row['round_no'])==expected

def permitted(c,rid,u):
    row=c.execute('SELECT * FROM writing_rounds WHERE id=?',(rid,)).fetchone()
    if not row or (u['role']!='teacher' and row['user_id']!=u['id']):raise HTTPException(404,'文档不存在')
    return row

def cache_source(rid,path,document):
    """Persist only complete bounded renderings; original document remains authoritative."""
    if not document.get('complete') or len(document.get('text',''))>60000:return
    data=Path(ENV['DATA']);key=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    folder=data/'writing-preview'/f'{rid}-{key}'
    pages=[]
    for n,p in enumerate(document.get('pages') or [{'page_no':1,'text':document.get('text','')}],1):
        page={'page_no':n,'text':p.get('text','')}
        image=p.get('image_path')
        if image and Path(image).is_file():
            folder.mkdir(parents=True,exist_ok=True,mode=0o700)
            destination=folder/f'{n}.jpg';shutil.copyfile(image,destination);page['_image']=str(destination)
        pages.append(page)
    source={'pages':pages,'warnings':document.get('warnings',[]),'text_only':not any('_image' in p for p in pages)}
    with ENV['db']() as c:c.execute('UPDATE writing_rounds SET source_json=? WHERE id=? AND path=?',(json.dumps(source,ensure_ascii=False),rid,path))

def locate(text,quote):
    positions=[i for i,ch in enumerate(text) if not ch.isspace()]
    needle=re.sub(r'\s+','',str(quote));haystack=''.join(text[i] for i in positions)
    start=haystack.find(needle) if len(needle)>=4 else -1
    if start<0 or haystack.find(needle,start+1)>=0:return None
    return positions[start],positions[start+len(needle)-1]+1

def public_source(c,row):
    import writing_workflow as w
    source=json.loads(row['source_json']);review=w.review_for(c,row) or {};anchors=[];pages=[]
    for p in source['pages']:
        page={'page_no':p['page_no'],'text':p['text']}
        if p.get('_image'):page['image_url']=f"/api/writing/rounds/{row['id']}/pages/{p['page_no']}"
        pages.append(page)
    for issue in review.get('issues',[]):
        if not issue.get('evidence_located'):continue
        needle=re.sub(r'\s+','',issue.get('quote',''))
        if len(needle)<4 or sum(re.sub(r'\s+','',p['text']).count(needle) for p in pages)!=1:continue
        for p in pages:
            found=locate(p['text'],issue.get('quote',''))
            if found:
                anchors.append({'issue_id':issue['id'],'page_no':p['page_no'],'start':found[0],'end':found[1]});break
    return {'assignment_id':row['assignment_id'],'submission_id':row['submission_id'],'round_id':row['id'],'filename':row['filename'],'round_no':row['round_no'],'pages':pages,'anchors':anchors,
            'warnings':source.get('warnings',[]),'text_only':source.get('text_only',True),
            'review':w.student_round(row,u_published(c,row),c)['review']}

def u_published(c,row):
    return bool(c.execute('SELECT published FROM submissions WHERE id=?',(row['submission_id'],)).fetchone()[0])

def cohort(c,aid):
    import writing_workflow as w
    a=w.assignment(c,aid);students=c.execute("SELECT u.id,u.name,u.student_no,m.ppt_presented,m.ppt_date,m.ppt_topic FROM users u JOIN course_memberships m ON m.user_id=u.id AND m.course_id='writing' AND m.active=1 WHERE u.role='student' AND u.deleted_at='' ORDER BY u.student_no").fetchall()
    if len(students)>1000:raise HTTPException(409,'班级人数超过当前清单上限，请先分课程管理')
    result=[]
    for s in students:
        item=dict(s);submission=c.execute('SELECT * FROM submissions WHERE assignment_id=? AND user_id=?',(aid,s['id'])).fetchone();rounds=[];pending=0
        for r in w.rows_for(c,aid,s['id']):
            review=w.review_for(c,r) or {};count=sum(bool(i.get('needs_review')) and not i.get('dismissed') for i in review.get('issues',[]));pending+=count
            rounds.append({'id':r['id'],'round_no':r['round_no'],'filename':r['filename'],'created':r['created'],'checked':bool(r['review_json']),
                'teacher_score':r['teacher_score'],'stale_grade':not bool(submission and submission['published']) and r['teacher_score'] is not None and not grade_current(r,a),'grade_published':bool(r['grade_published']),'needs_review':count})
        item.update(rounds=rounds,submission_id=submission['id'] if submission else None,status=submission['status'] if submission else '尚未提交',
            published=bool(submission and submission['published']),grading=writing_scores.aggregate(c,submission['id']) if submission else None,
            needs_review=pending,unconfirmed=0 if submission and submission['published'] else sum(r['checked'] and (r['teacher_score'] is None or r['stale_grade']) for r in rounds))
        result.append(item)
    a['rubric']=json.loads(a['rubric']);a['stage_rubrics']=json.loads(a['stage_rubrics']);a['round_weights']=json.loads(a['round_weights'])
    return {'assignment':a,'students':result}

class Batch(BaseModel):
    action:Literal['draft','publish_rounds','publish_totals']
    student_ids:list[int]=Field(default_factory=list,max_length=1000)
    token:str=Field(default='',max_length=100)

def batch_plan(c,aid,x):
    import writing_workflow as w
    data=cohort(c,aid);a=data['assignment'];items=[];skipped=[];versions=[]
    selected=set(x.student_ids)
    if selected-set(s['id'] for s in data['students']):raise HTTPException(400,'选中的学生不属于本课程')
    for student in data['students']:
        if selected and student['id'] not in selected:continue
        sid=student['submission_id'];rows=w.rows_for(c,aid,student['id'])
        versions.extend([{k:r[k] for k in ('id','path','teacher_score','teacher_feedback','grade_published','graded_at','graded_revision','graded_policy')}|{'review_hash':hashlib.sha256((r['review_json'] or '').encode()).hexdigest(),'snapshot_hash':hashlib.sha256(r['assignment_snapshot'].encode()).hexdigest()} for r in rows]);versions.append({'sid':sid,'status':student['status'],'published':student['published']})
        common='总成绩已发布' if student['published'] else 'AI任务处理中' if student['status'] in ENV['BUSY'] else ''
        if sid:
            submission=c.execute('SELECT * FROM submissions WHERE id=?',(sid,)).fetchone()
            if submission['returned']:common='稿件已退回'
        def skip(reason,number=None):skipped.append({'name':student['name'],'student_no':student['student_no'],'round_no':number,'reason':reason})
        if x.action=='publish_totals':
            total=student.get('grading') or {}
            if common:skip(common);continue
            if len(rows)!=4 or total.get('total') is None or not rows[-1]['review_json']:skip('四轮提交或有权重轮次的教师分数未齐');continue
            if student['needs_review']:skip('尚有意见待教师核验');continue
            if any(r['teacher_score'] is not None and not grade_current(r,a) for r in rows if a['round_weights'][r['round_no']-1]>0):skip('评分标准有变化，请重新确认分轮成绩');continue
            items.append({'submission_id':sid,'user_id':student['id'],'name':student['name'],'student_no':student['student_no'],'score':total['total']});continue
        if not rows:skip('尚未提交');continue
        for r in rows:
            number=r['round_no'];review=w.review_for(c,r) or {}
            if common:skip(common,number);continue
            if not r['review_json']:skip('本轮尚未检查',number);continue
            if any(i.get('needs_review') and not i.get('dismissed') for i in review.get('issues',[])):skip('意见待核验，请先处理',number);continue
            if x.action=='draft':
                if r['teacher_score'] is not None:skip('已有教师分数，保留不覆盖',number);continue
                score=review.get('score');dims=review.get('dimensions') or []
                if type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=100 or not dims or abs(sum(d.get('max',0) for d in dims)-100)>.001 or abs(sum(d.get('score',0) for d in dims)-score)>.011 or any(not d.get('quote_verified') or not d.get('comment','').strip() for d in dims):skip('建议分或评分依据不完整',number);continue
                if not review.get('scoring_basis') or policy_hash(review['scoring_basis'],number)!=policy_hash(a,number):skip('采用旧版标准，需教师单独确认',number);continue
            else:
                if r['teacher_score'] is None:skip('缺少教师评分草稿',number);continue
                if not grade_current(r,a):skip('评分标准有变化，请重新确认',number);continue
                if r['grade_published']:skip('本轮成绩已发布',number);continue
                score=r['teacher_score']
            items.append({'round_id':r['id'],'submission_id':sid,'user_id':student['id'],'name':student['name'],'student_no':student['student_no'],'round_no':number,'score':score})
    token=hashlib.sha256(json.dumps({'action':x.action,'aid':aid,'selected':sorted(selected),'assignment':a,'versions':versions,'items':items,'skipped':skipped},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'action':x.action,'token':token,'items':items,'skipped':skipped}

def register(app,env):
    global ENV
    ENV=env;db=lambda:env['db']();current=env['current'];teacher=env['teacher']

    @app.get('/api/writing/templates')
    def templates(u=Depends(current)):return {'stage_rubrics':DEFAULT_RUBRICS}

    @app.get('/api/writing/rounds/{rid}/source')
    def source(rid:int,u=Depends(current)):
        with db() as c:r=permitted(c,rid,u)
        env['throttle']('writing-source:'+str(u['id']),100 if u['role']=='teacher' else 30,3600)
        if not r['source_json']:
            if not PREVIEW_SLOT.acquire(blocking=False):raise HTTPException(409,'正在准备其他文档预览，请稍后重试')
            try:
                if Path(r['path']).suffix.lower()=='.docx':
                    from docx import Document
                    document=Document(r['path']);parts=[p.text for p in document.paragraphs]
                    parts.extend(' | '.join(cell.text for cell in row.cells) for t in document.tables for row in t.rows)
                    text='\n'.join(parts)
                    if len(text)>60000:raise ValueError()
                    cache_source(rid,r['path'],{'complete':True,'text':text,'warnings':['当前为Word文字视图，表格另列；版式与图片请下载原稿查看。AI检查完成后可显示服务器排版图。']})
                else:
                    with env['prepare_document'](r['path']) as prepared:cache_source(rid,r['path'],prepared)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Document preview failed round=%s',rid)
                raise HTTPException(422,'暂不能生成在线对照，请先下载原文件查看；不会影响提交和评分')
            finally:PREVIEW_SLOT.release()
        with db() as c:
            r=permitted(c,rid,u)
            if not r['source_json']:raise HTTPException(409,'文件已更新，请刷新后重新预览')
            return public_source(c,r)

    @app.get('/api/writing/rounds/{rid}/pages/{number}')
    def page(rid:int,number:int,u=Depends(current)):
        with db() as c:r=permitted(c,rid,u)
        pages=json.loads(r['source_json'] or '{}').get('pages',[]);p=next((p for p in pages if p['page_no']==number),{})
        path=Path(p.get('_image','')).resolve();root=(Path(env['DATA'])/'writing-preview').resolve()
        if not path.is_relative_to(root) or not path.is_file():raise HTTPException(404,'排版图暂不可用')
        return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})

    @app.get('/api/teacher/writing/assignments/{aid}/cohort')
    def worklist(aid:int,u=Depends(teacher)):
        with db() as c:return cohort(c,aid)

    @app.post('/api/teacher/writing/assignments/{aid}/batch-preview')
    def preview(aid:int,x:Batch,u=Depends(teacher)):
        with db() as c:return batch_plan(c,aid,x)

    @app.post('/api/teacher/writing/assignments/{aid}/batch-apply')
    def apply(aid:int,x:Batch,u=Depends(teacher)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');plan=batch_plan(c,aid,x)
            assignment=dict(c.execute('SELECT * FROM assignments WHERE id=?',(aid,)).fetchone());revision=assignment['revision']
            if not x.token or x.token!=plan['token']:raise HTTPException(409,'评分或提交已变化，请重新预览后确认')
            affected=set()
            for item in plan['items']:
                sid=item['submission_id'];affected.add(sid)
                if x.action=='draft':
                    r=c.execute('SELECT review_json FROM writing_rounds WHERE id=?',(item['round_id'],)).fetchone();feedback=json.loads(r[0]).get('summary','')
                    c.execute('UPDATE writing_rounds SET teacher_score=?,teacher_feedback=?,grade_published=0,graded_at=?,graded_by=?,graded_revision=?,graded_policy=? WHERE id=?',(item['score'],feedback,env['now'](),u['id'],revision,policy_hash(assignment,item['round_no']),item['round_id']))
                elif x.action=='publish_rounds':c.execute('UPDATE writing_rounds SET grade_published=1,graded_at=?,graded_by=? WHERE id=?',(env['now'](),u['id'],item['round_id']))
                else:c.execute("UPDATE submissions SET score=?,published=1,status='已发布' WHERE id=?",(item['score'],sid))
            if x.action!='publish_totals':
                for sid in affected:
                    total=writing_scores.aggregate(c,sid)
                    if total['completed_rounds']==4:c.execute('UPDATE submissions SET score=? WHERE id=? AND published=0',(total['total'],sid))
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'writing-batch-'+x.action,json.dumps({'assignment':aid,'items':plan['items']},ensure_ascii=False),env['now']()))
        return {'ok':True,'affected':len(plan['items']),'skipped':len(plan['skipped'])}

    @app.get('/api/writing/assignments/{aid}/portfolio')
    def portfolio(aid:int,user_id:int|None=None,u=Depends(current)):
        import writing_workflow as w
        uid=u['id'] if user_id is None else user_id
        if uid!=u['id'] and u['role']!='teacher':raise HTTPException(403,'只能下载自己的学习档案')
        with db() as c:
            a=w.assignment(c,aid);student=c.execute("SELECT id,name,student_no FROM users WHERE id=? AND role='student'",(uid,)).fetchone()
            if not student:raise HTTPException(404,'学生不存在')
            rows=w.rows_for(c,aid,uid)
            if not rows:raise HTTPException(404,'尚无提交记录')
            s=c.execute('SELECT * FROM submissions WHERE assignment_id=? AND user_id=?',(aid,uid)).fetchone();visible=u['role']=='teacher' or bool(s['published'])
            rounds=[]
            for row in rows:
                item=w.student_round(row,visible,c);item['assignment_snapshot']=json.loads(row['assignment_snapshot'])
                item['responses']=[dict(x) for x in c.execute('SELECT issue_id,decision,reason,updated FROM writing_responses WHERE round_id=?',(row['id'],))]
                rounds.append(item)
            method=c.execute('SELECT reminders,confirmed FROM writing_method_cards WHERE assignment_id=? AND user_id=?',(aid,uid)).fetchone()
            surveys=[dict(x) for x in c.execute('SELECT moment,answers,updated FROM writing_surveys WHERE assignment_id=? AND user_id=?',(aid,uid))]
            grading=writing_scores.aggregate(c,s['id'],public=u['role']!='teacher')
        record={'exported_at':env['now'](),'student':dict(student),'assignment':{'title':a['title'],'instructions':a['instructions'],'stage_rubrics':json.loads(a['stage_rubrics'])},'grading':grading,'rounds':rounds,'surveys':surveys,'method':dict(method) if method else None,'published':bool(s['published']),'score':s['score'] if visible else None,'files':[]}
        spool=tempfile.SpooledTemporaryFile(max_size=4*1024*1024);size=0
        try:
            with zipfile.ZipFile(spool,'w',zipfile.ZIP_DEFLATED) as z:
                for row in rows:
                    path=Path(row['path']).resolve();root=(Path(env['DATA'])/'files').resolve()
                    if not path.is_relative_to(root) or not path.is_file():raise HTTPException(409,'原稿缺失，请联系教师；未生成不完整档案')
                    size+=path.stat().st_size
                    if size>64*1024*1024:raise HTTPException(409,'档案过大，请分别下载原文')
                    name=f"round-{row['round_no']}/original{path.suffix.lower()}"
                    try:content=path.read_bytes()
                    except OSError:raise HTTPException(409,'原稿正在更新，请刷新后重新下载档案')
                    z.writestr(name,content)
                    record['files'].append({'round_no':row['round_no'],'original_filename':row['filename'],'entry':name,'sha256':hashlib.sha256(content).hexdigest()})
                z.writestr('learning-record.json',json.dumps(record,ensure_ascii=False,indent=2))
                esc=lambda x:html.escape(str('' if x is None else x))
                sections=[]
                for r in rounds:
                    review=r.get('review') or {};sections.append(f"<section><h2>第{r['round_no']}轮</h2><p>教师分数：{esc(r['teacher_score']) if r['teacher_score'] is not None else '未发布'}</p><p>{esc(review.get('summary','尚未检查'))}</p><p>教师评语：{esc(r.get('teacher_feedback',''))}</p><p>本轮标准：{esc('；'.join(str(x['name'])+' '+str(x['max'])+'分' for x in r['assignment_snapshot']['rubric']))}</p>"+''.join(f"<article><h3>{esc(i.get('problem'))}</h3><blockquote>{esc(i.get('quote'))}</blockquote><p>{esc(i.get('suggestion'))}</p></article>" for i in review.get('issues',[]))+''.join(f"<p>修改回应：{esc(v['decision'])}；{esc(v['reason'])}</p>" for v in r['responses'])+'</section>')
                page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>我的写作学习档案</title><style>body{max-width:900px;margin:40px auto;padding:20px;font:16px/1.8 sans-serif;color:#20344a}section{border-top:1px solid #ddd;margin-top:30px}blockquote{border-left:3px solid #abc;padding-left:16px;white-space:pre-wrap}article{margin:20px 0}p{white-space:pre-wrap}</style><h1>'+esc(a['title'])+'</h1><p>'+esc(student['name'])+' · '+esc(student['student_no'])+'</p><p>四轮权重：'+esc(' / '.join(str(x)+'%' for x in grading['weights']))+'；总成绩：'+(esc(s['score']) if s['published'] else '未发布')+'</p><p>原稿保留在各round文件夹。修改说明与AI使用声明以本人上传文档为准。未发布的教师分数不会出现在学生档案中。</p>'+''.join(sections)+'<h2>我的写作方法卡</h2><p>'+esc('\n'.join(json.loads(method['reminders'])) if method else '尚未填写')+'</p></html>'
                z.writestr('打开学习档案.html',page)
            spool.seek(0)
        except Exception:spool.close();raise
        def stream():
            try:
                while chunk:=spool.read(65536):yield chunk
            finally:spool.close()
        return StreamingResponse(stream(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="writing-portfolio-{aid}-{uid}.zip"'})
