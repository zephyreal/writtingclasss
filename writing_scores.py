"""Teacher-confirmed per-round scores and deterministic weighted aggregation."""
import json
import math
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field

DEFAULT_WEIGHTS=[25,25,25,25]

def weights(value):
    if not isinstance(value,list) or len(value)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) or x<0 or x>100 for x in value) or abs(sum(value)-100)>.001:raise HTTPException(400,'请填写四轮权重，均为0—100且合计100%')
    return [float(x) for x in value]

def migrate(c):
    cols={r['name'] for r in c.execute('PRAGMA table_info(assignments)')}
    if 'round_weights' not in cols:c.execute("ALTER TABLE assignments ADD COLUMN round_weights TEXT NOT NULL DEFAULT '[0,0,0,100]'")
    cols={r['name'] for r in c.execute('PRAGMA table_info(writing_rounds)')}
    for name,definition in [('teacher_score','REAL'),('teacher_feedback',"TEXT NOT NULL DEFAULT ''"),('grade_published','INTEGER NOT NULL DEFAULT 0'),('graded_at',"TEXT NOT NULL DEFAULT ''"),('graded_by','INTEGER')]:
        if name not in cols:c.execute(f'ALTER TABLE writing_rounds ADD COLUMN {name} {definition}')
    c.execute('''UPDATE writing_rounds SET teacher_score=(SELECT score FROM submissions WHERE id=submission_id),
        teacher_feedback=(SELECT feedback FROM submissions WHERE id=submission_id),
        grade_published=(SELECT published FROM submissions WHERE id=submission_id)
        WHERE round_no=4 AND teacher_score IS NULL AND submission_id IN
        (SELECT s.id FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE a.round_weights='[0,0,0,100]' AND s.score IS NOT NULL)''')

def aggregate(c,sid,public=False):
    row=c.execute('SELECT a.round_weights,s.published FROM assignments a JOIN submissions s ON s.assignment_id=a.id WHERE s.id=?',(sid,)).fetchone()
    if not row:return None
    ww=weights(json.loads(row['round_weights']));rows=c.execute('SELECT * FROM writing_rounds WHERE submission_id=? ORDER BY round_no',(sid,)).fetchall()
    scores={r['round_no']:r['teacher_score'] for r in rows if r['teacher_score'] is not None and (not public or r['grade_published'] or row['published'])}
    missing=[n for n,w in enumerate(ww,1) if w>0 and n not in scores]
    total=round(sum(scores.get(n,0)*w/100 for n,w in enumerate(ww,1)),2) if not missing and len(rows)==4 else None
    if public and not row['published']:total=None
    return {'weights':ww,'total':total,'missing':missing,'completed_rounds':len(rows),'confirmed_rounds':len(scores)}

class RoundGrade(BaseModel):
    score:float=Field(ge=0,le=100,allow_inf_nan=False)
    feedback:str=Field(default='',max_length=10000)
    published:bool=False

def final_score(c,sid,x,uid,stamp):
    a=c.execute('SELECT a.workflow,a.round_weights FROM assignments a JOIN submissions s ON s.assignment_id=a.id WHERE s.id=?',(sid,)).fetchone()
    if not a or not a['workflow']:return x.score
    from writing_workflow import require_final
    require_final(c,sid)
    ww=weights(json.loads(a['round_weights']))
    # Old assignments retain their original final-only grading semantics.
    if ww==[0,0,0,100]:
        c.execute('UPDATE writing_rounds SET teacher_score=?,teacher_feedback=?,grade_published=?,graded_at=?,graded_by=? WHERE submission_id=? AND round_no=4',(x.score,x.feedback,int(x.published),stamp,uid,sid))
    total=aggregate(c,sid)
    if total['total'] is None:raise HTTPException(409,'请先填写所有有权重轮次的教师分数，并完成四次提交')
    if ww!=[0,0,0,100] and abs(x.score-total['total'])>.011:raise HTTPException(409,'总分须按四轮教师分数和权重计算，请刷新后保存')
    return total['total']

def register(app,env):
    db=lambda:env['db']();teacher=env['teacher']
    @app.post('/api/teacher/writing/rounds/{rid}/grade')
    def grade(rid:int,x:RoundGrade,u=Depends(teacher)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute("SELECT w.*,s.published AS final_published,s.status FROM writing_rounds w JOIN submissions s ON s.id=w.submission_id JOIN assignments a ON a.id=w.assignment_id JOIN users u ON u.id=w.user_id WHERE w.id=? AND a.deleted_at='' AND u.deleted_at=''",(rid,)).fetchone()
            if not r:raise HTTPException(404,'轮次不存在')
            if r['final_published']:raise HTTPException(409,'总成绩已发布，请先撤回总成绩后修改分轮评分')
            if r['status'] in env['BUSY']:raise HTTPException(409,'AI任务处理中，请等待完成后评分')
            if not r['review_json']:raise HTTPException(409,'请先完成本轮AI检查或保存人工反馈')
            c.execute('UPDATE writing_rounds SET teacher_score=?,teacher_feedback=?,grade_published=?,graded_at=?,graded_by=? WHERE id=?',(x.score,x.feedback,int(x.published),env['now'](),u['id'],rid))
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'writing-round-grade',json.dumps({'round':rid,'score':x.score,'published':x.published}),env['now']()))
            total=aggregate(c,r['submission_id'])
            # Draft totals are never silently published.
            c.execute('UPDATE submissions SET score=? WHERE id=? AND published=0',(total['total'],r['submission_id'])) if total['completed_rounds']==4 else None
        return {'ok':True,'grading':total}
