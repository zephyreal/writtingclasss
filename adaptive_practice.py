"""Thirty-item timed practice. Partial sessions are temporary, never learning records."""
import json
import logging
import secrets
import time
from collections import Counter,defaultdict
from fastapi import BackgroundTasks,Depends,HTTPException
from pydantic import BaseModel,Field,StrictInt
from practice_bank import BANK,BANK_VERSION,TOPICS

clock=time.time
RNG=secrets.SystemRandom()
SIZE=30
SECONDS=10

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS practice_pending(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),created REAL NOT NULL,expires REAL NOT NULL,position INTEGER NOT NULL,deadline REAL NOT NULL,items TEXT NOT NULL,answers TEXT NOT NULL,source TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS practice_pending_user ON practice_pending(user_id);
    CREATE TABLE IF NOT EXISTS practice_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,token TEXT UNIQUE NOT NULL,user_id INTEGER REFERENCES users(id),started REAL NOT NULL,completed REAL NOT NULL,source TEXT NOT NULL,correct INTEGER NOT NULL,timeouts INTEGER NOT NULL,items TEXT NOT NULL,plan TEXT NOT NULL DEFAULT '{}',bank_version TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS practice_runs_user ON practice_runs(user_id,id);
    CREATE TABLE IF NOT EXISTS practice_generation(user_id INTEGER PRIMARY KEY REFERENCES users(id),generation INTEGER NOT NULL DEFAULT 0);
    ''')

def evidence(c,uid):
    # Bound memory and model context; all reports still retain complete snapshots.
    rows=c.execute('SELECT items FROM practice_runs WHERE user_id=? ORDER BY id DESC LIMIT 8',(uid,)).fetchall()
    stats=defaultdict(lambda:{'n':0,'correct':0,'timeouts':0,'wrong':0})
    seen=Counter();last=set()
    for i,row in enumerate(rows):
        for q in json.loads(row['items']):
            seen[q['id']]+=1
            if not i:last.add(q['id'])
            s=stats[q['topic']];s['n']+=1;s['correct']+=int(q['correct']);s['timeouts']+=int(q['timed_out']);s['wrong']+=int(not q['correct'] and not q['timed_out'])
    return stats,seen,last

def choose(c,uid):
    stats,seen,last=evidence(c,uid)
    latest=c.execute('SELECT plan FROM practice_runs WHERE user_id=? ORDER BY id DESC LIMIT 1',(uid,)).fetchone()
    if not latest:
        units=list(range(1,9));RNG.shuffle(units);picked=[]
        # 4x6 + 3x2 = 30, with the smaller groups rotating randomly.
        for i,unit in enumerate(units):
            for level,n in ((1,1),(2,2 if i<6 else 1),(3,1)):
                picked+=RNG.sample([q for q in BANK.values() if q['chapter_id']==unit and q['level']==level],n)
        RNG.shuffle(picked);source='random'
    else:
        plan=json.loads(latest['plan']);priority=plan.get('topics',[]);level=plan.get('level',2)
        source='ai' if priority else 'rules';picked=[];ids=set()
        ranked=list(stats);RNG.shuffle(ranked)
        ranked.sort(key=lambda t:(stats[t]['wrong']/(stats[t]['n']-stats[t]['timeouts']+2),stats[t]['wrong']),reverse=True)
        focus_topics=set(priority or [t for t in ranked if stats[t]['wrong']][:8])
        global_observed=sum(s['n']-s['timeouts'] for s in stats.values())
        global_correct=sum(s['correct'] for s in stats.values())
        global_level=(3 if global_correct/global_observed>.85 else 1 if global_correct/global_observed<.5 else 2) if global_observed>=15 else 2
        def weight(q,focus):
            s=stats[q['topic']];observed=s['n']-s['timeouts']
            # A timeout is not treated as proof of a conceptual misconception.
            weakness=(s['wrong']+1)/(observed+2)
            w=1+4*weakness+(3 if q['topic'] in priority else 0)
            if focus and q['topic'] not in priority and stats and s['n']==0:w*=.7
            target=level if priority else (1 if observed>=3 and s['correct']/observed<.5 else 3 if observed>=3 and s['correct']/observed>.85 else global_level)
            w*=1.7 if q['level']==target else 1
            w/=1+seen[q['id']]*3
            if q['id'] in last:w*=.1
            return w
        # Eight broad review items prevent narrow drilling; the other 22 emphasize need.
        for unit in range(1,9):
            pool=[q for q in BANK.values() if q['chapter_id']==unit and q['id'] not in ids]
            q=RNG.choices(pool,weights=[weight(q,False) for q in pool],k=1)[0];picked.append(q);ids.add(q['id'])
        while len(picked)<SIZE:
            pool=[q for q in BANK.values() if q['id'] not in ids]
            focused=[q for q in pool if q['topic'] in focus_topics]
            if len(picked)<22 and focused:pool=focused
            q=RNG.choices(pool,weights=[weight(q,True) for q in pool],k=1)[0];picked.append(q);ids.add(q['id'])
        RNG.shuffle(picked)
    snapshots=[]
    for q in picked:
        item=dict(q);item['bank_version']=BANK_VERSION;order=list(range(len(q['options'])));RNG.shuffle(order)
        item['options']=[q['options'][i] for i in order];item['answer']=order.index(q['answer']);snapshots.append(item)
    return snapshots,source

def summary(row):
    return {'id':row['id'],'completed':row['completed'],'started':row['started'],'correct':row['correct'],'total':SIZE,'timeouts':row['timeouts'],'score':round(row['correct']/SIZE*100,1),'source':row['source']}

def result(row):
    r=summary(row);items=json.loads(row['items']);misses=Counter(q['topic_name'] for q in items if not q['correct'] and not q['timed_out'])
    r.update(items=items,focus=[name for name,_ in misses.most_common(3)],planning=bool(json.loads(row['plan']).get('topics')))
    return r

def public_pending(row):
    q=json.loads(row['items'])[row['position']]
    return {'token':row['token'],'position':row['position'],'total':SIZE,'seconds':SECONDS,'deadline':row['deadline'],'server_now':clock(),'question':{k:q[k] for k in ('id','chapter_id','stem','options','kind')},'source':row['source']}

def overview(c,uid):
    row=c.execute('SELECT COUNT(*) n,SUM(correct) correct,SUM(timeouts) timeouts FROM practice_runs WHERE user_id=?',(uid,)).fetchone()
    latest=c.execute('SELECT * FROM practice_runs WHERE user_id=? ORDER BY id DESC LIMIT 1',(uid,)).fetchone()
    return {'rounds':row['n'],'answered':row['n']*SIZE,'correct':row['correct'] or 0,'timeouts':row['timeouts'] or 0,'accuracy':round((row['correct'] or 0)/(row['n']*SIZE)*100,1) if row['n'] else None,'latest':summary(latest) if latest else None}

def unit_profile(c,uid):
    stats,_,_=evidence(c,uid)
    units=[]
    for ch in c.execute('SELECT id,title FROM chapters ORDER BY id'):
        ss=[v for k,v in stats.items() if TOPICS.get(k,{}).get('chapter_id')==ch['id']]
        n=sum(x['n'] for x in ss);correct=sum(x['correct'] for x in ss);timeouts=sum(x['timeouts'] for x in ss)
        units.append({'id':ch['id'],'title':ch['title'],'questions':n,'correct':correct,'timeouts':timeouts,'accuracy':round(correct/n*100,1) if n else None})
    return units

class Step(BaseModel):
    position:StrictInt=Field(ge=0,lt=SIZE)
    choice:StrictInt|None=Field(default=None,ge=0,le=2)
class Management(BaseModel):
    reason:str=Field(min_length=2,max_length=300)

def register(app,env):
    db=lambda:env['db']()
    current=env['current'];teacher=env['teacher']

    def plan_next(uid,rid,generation):
        try:
            cfg=env['ai_settings']()
            if not cfg.get('key') or not cfg.get('model'):return
            with db() as c:
                if not c.execute('SELECT 1 FROM practice_runs WHERE id=? AND user_id=?',(rid,uid)).fetchone():return
                stats,_,_=evidence(c,uid)
            # No student names, text, paper files, or answer generation are sent.
            signals=[{**TOPICS[t],**s} for t,s in stats.items() if t in TOPICS]
            response=env['ai_call']('你是学术写作练习教练。仅依据答题统计从给定topic id中选择下一轮应重点练习的最多8项，按优先级排序；超时不是知识错误，不要给学生贴能力标签。返回JSON：topics字符串数组，level为1至3的整数。禁止生成题目、答案、分数或个人评价。',{'performance':signals,'_usage_context':{'user_id':uid,'purpose':'30题后续练习安排','timeout':12,'max_tokens':350}})
            topics=response.get('topics');level=response.get('level')
            if not isinstance(topics,list) or not 1<=len(topics)<=8 or any(type(t) is not str or t not in {s['id'] for s in signals} for t in topics) or len(set(topics))!=len(topics) or type(level) is not int or level not in (1,2,3):return
            with db() as c:
                c.execute('UPDATE practice_runs SET plan=? WHERE id=? AND user_id=? AND ?=(SELECT generation FROM practice_generation WHERE user_id=?)', (json.dumps({'topics':topics,'level':level}),rid,uid,generation,uid))
        except Exception:
            logging.getLogger(__name__).info('Practice planner unavailable; using recorded-answer recommendations for run %s',rid)

    @app.get('/api/practice/session')
    def state(u=Depends(current)):
        with db() as c:
            c.execute('DELETE FROM practice_pending WHERE expires<?',(clock(),))
            p=c.execute('SELECT * FROM practice_pending WHERE user_id=?',(u['id'],)).fetchone()
            runs=[summary(r) for r in c.execute('SELECT * FROM practice_runs WHERE user_id=? ORDER BY id DESC LIMIT 20',(u['id'],))]
            return {'active':public_pending(p) if p else None,'records':runs,'summary':overview(c,u['id']),'bank_count':len(BANK),'unit_count':8,'per_unit':80}

    @app.post('/api/practice/session')
    def start(u=Depends(current)):
        env['throttle']('practice-round-start:'+str(u['id']),30,3600)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');c.execute('DELETE FROM practice_pending WHERE expires<?',(clock(),))
            p=c.execute('SELECT * FROM practice_pending WHERE user_id=?',(u['id'],)).fetchone()
            if p:return public_pending(p)
            items,source=choose(c,u['id']);stamp=clock();token=secrets.token_urlsafe(24)
            c.execute('INSERT INTO practice_pending VALUES(?,?,?,?,?,?,?,?,?)',(token,u['id'],stamp,stamp+1200,0,stamp+SECONDS,json.dumps(items,ensure_ascii=False),'[]',source))
            c.execute('INSERT OR IGNORE INTO practice_generation(user_id) VALUES(?)',(u['id'],))
            return public_pending(c.execute('SELECT * FROM practice_pending WHERE token=?',(token,)).fetchone())

    @app.post('/api/practice/session/{token}/answer')
    def answer(token:str,x:Step,background:BackgroundTasks,u=Depends(current)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            done=c.execute('SELECT * FROM practice_runs WHERE token=? AND user_id=?',(token,u['id'])).fetchone()
            if done:return {'finished':True,'result':result(done)}
            p=c.execute('SELECT * FROM practice_pending WHERE token=? AND user_id=?',(token,u['id'])).fetchone()
            if not p or p['expires']<clock():raise HTTPException(404,'本轮已结束或已退出，请重新开始；未完成内容未计入记录')
            if x.position<p['position']:return {'finished':False,'active':public_pending(p)}
            if x.position!=p['position']:raise HTTPException(409,'题目顺序已变化，请刷新当前题')
            items=json.loads(p['items']);q=items[x.position]
            if x.choice is not None and x.choice>=len(q['options']):raise HTTPException(400,'请选择有效选项')
            stamp=clock();timed_out=stamp>=p['deadline']
            if x.choice is None and not timed_out:raise HTTPException(409,'当前题目尚未到时')
            choice=None if timed_out else x.choice
            q.update(choice=choice,timed_out=timed_out,correct=choice==q['answer'],elapsed=round(min(SECONDS,max(0,stamp-(p['deadline']-SECONDS))),3))
            answers=json.loads(p['answers']);answers.append(q)
            if len(answers)<SIZE:
                c.execute('UPDATE practice_pending SET position=position+1,deadline=?,answers=? WHERE token=?',(stamp+SECONDS,json.dumps(answers,ensure_ascii=False),token))
                return {'finished':False,'active':public_pending(c.execute('SELECT * FROM practice_pending WHERE token=?',(token,)).fetchone())}
            rid=c.execute('INSERT INTO practice_runs(token,user_id,started,completed,source,correct,timeouts,items,bank_version) VALUES(?,?,?,?,?,?,?,?,?)',(token,u['id'],p['created'],stamp,p['source'],sum(q['correct'] for q in answers),sum(q['timed_out'] for q in answers),json.dumps(answers,ensure_ascii=False),answers[0].get('bank_version',BANK_VERSION))).lastrowid
            c.execute('DELETE FROM practice_pending WHERE token=?',(token,))
            generation=c.execute('SELECT generation FROM practice_generation WHERE user_id=?',(u['id'],)).fetchone()[0]
            saved=c.execute('SELECT * FROM practice_runs WHERE id=?',(rid,)).fetchone();output=result(saved)
        background.add_task(plan_next,u['id'],rid,generation)
        return {'finished':True,'result':output}

    @app.delete('/api/practice/session/{token}')
    def abandon(token:str,u=Depends(current)):
        with db() as c:c.execute('DELETE FROM practice_pending WHERE token=? AND user_id=?',(token,u['id']))
        return {'ok':True}

    @app.get('/api/practice/records/{rid}')
    def record(rid:int,u=Depends(current)):
        with db() as c:r=c.execute('SELECT * FROM practice_runs WHERE id=? AND user_id=?',(rid,u['id'])).fetchone()
        if not r:raise HTTPException(404,'练习记录不存在')
        return result(r)

    @app.get('/api/teacher/practice/students')
    def students(u=Depends(teacher)):
        with db() as c:return [{**dict(s),'practice':overview(c,s['id'])} for s in c.execute("SELECT id,name,student_no FROM users WHERE role='student' ORDER BY student_no")]

    @app.get('/api/teacher/practice/students/{uid}')
    def records(uid:int,u=Depends(teacher)):
        with db() as c:
            s=c.execute("SELECT id,name,student_no FROM users WHERE id=? AND role='student'",(uid,)).fetchone()
            if not s:raise HTTPException(404,'学生不存在')
            return {'student':dict(s),'summary':overview(c,uid),'records':[summary(r) for r in c.execute('SELECT * FROM practice_runs WHERE user_id=? ORDER BY id DESC LIMIT 200',(uid,))]}

    @app.get('/api/teacher/practice/records/{rid}')
    def teacher_record(rid:int,u=Depends(teacher)):
        with db() as c:r=c.execute('SELECT * FROM practice_runs WHERE id=?',(rid,)).fetchone()
        if not r:raise HTTPException(404,'练习记录不存在')
        return result(r)

    def invalidate(c,uid):
        c.execute('INSERT OR IGNORE INTO practice_generation(user_id) VALUES(?)',(uid,))
        c.execute('UPDATE practice_generation SET generation=generation+1 WHERE user_id=?',(uid,))
        c.execute('UPDATE practice_runs SET plan=\'{}\' WHERE user_id=?',(uid,))
        c.execute('DELETE FROM practice_pending WHERE user_id=?',(uid,))

    @app.delete('/api/teacher/practice/records/{rid}')
    def delete(rid:int,x:Management,u=Depends(teacher)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT user_id FROM practice_runs WHERE id=?',(rid,)).fetchone()
            if not r:raise HTTPException(404,'练习记录不存在')
            c.execute('DELETE FROM practice_runs WHERE id=?',(rid,));invalidate(c,r['user_id'])
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'practice-delete',json.dumps({'record':rid,'student':r['user_id'],'reason':x.reason},ensure_ascii=False),env['now']()))
        return {'ok':True}

    @app.post('/api/teacher/practice/students/{uid}/reset')
    def reset(uid:int,x:Management,u=Depends(teacher)):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='student'",(uid,)).fetchone():raise HTTPException(404,'学生不存在')
            count=c.execute('DELETE FROM practice_runs WHERE user_id=?',(uid,)).rowcount;invalidate(c,uid)
            c.execute('INSERT INTO audit(user_id,action,target,created) VALUES(?,?,?,?)',(u['id'],'practice-reset',json.dumps({'student':uid,'records':count,'reason':x.reason},ensure_ascii=False),env['now']()))
        return {'ok':True,'deleted':count}
