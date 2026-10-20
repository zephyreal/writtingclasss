"""Persistent, single-worker paper review queue. All clock inputs are explicit BJT."""
import threading
import time
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

BJT=timezone(timedelta(hours=8))
BUSY=('AI排队中','AI批改中','AI定时待批改')

class DeferReview(Exception):pass
class DailyQuotaExceeded(ValueError):
    def __init__(self,message,retry_at):
        super().__init__(message);self.retry_at=retry_at


def next_daily(clock,stamp=None):
    current=datetime.fromtimestamp(time.time() if stamp is None else stamp,BJT)
    hour,minute=map(int,clock.split(':'))
    result=current.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if result<=current:result+=timedelta(days=1)
    return result.timestamp()


def peak(stamp):
    current=datetime.fromtimestamp(stamp,BJT)
    # Conservative: do not assume a weekday is a statutory holiday.
    minute=current.hour*60+current.minute
    return current.weekday()<5 and (540<=minute<720 or 840<=minute<1080)


class ReviewQueue:
    def __init__(self,db,pool,review,settings):
        self.db,self.pool,self.review,self.settings=db,pool,review,settings
        self.slot=threading.Lock();self.stop_event=threading.Event();self.thread=None
        with db() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS paper_review_jobs(id INTEGER PRIMARY KEY,submission_id INTEGER NOT NULL,path TEXT NOT NULL,run_at REAL NOT NULL,state TEXT NOT NULL DEFAULT 'pending',previous_status TEXT NOT NULL,created REAL NOT NULL,finished REAL,error TEXT NOT NULL DEFAULT '');
            CREATE UNIQUE INDEX IF NOT EXISTS paper_review_active ON paper_review_jobs(submission_id) WHERE state IN ('pending','running');
            CREATE INDEX IF NOT EXISTS paper_review_due ON paper_review_jobs(state,run_at,id);
            ''')
            # Do not silently rebill an interrupted running request after a restart.
            c.execute("UPDATE submissions SET status='AI任务中断，可重新批改' WHERE id IN (SELECT submission_id FROM paper_review_jobs WHERE state='running') AND status='AI批改中'")
            c.execute("UPDATE paper_review_jobs SET state='failed',error='服务重启中断，请教师确认后重试',finished=? WHERE state='running'",(time.time(),))
            for row in c.execute("SELECT submission_id,path,run_at FROM paper_review_jobs WHERE state='pending'").fetchall():
                c.execute('UPDATE submissions SET status=? WHERE id=? AND path=?',('AI定时待批改' if row['run_at']>time.time() else 'AI排队中',row['submission_id'],row['path']))

    def enqueue(self,sid,run_at=None,replace_ai=False,wake=True):
        due=time.time() if run_at is None else run_at
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            s=c.execute('SELECT s.* FROM submissions s JOIN assignments a ON a.id=s.assignment_id AND a.deleted_at="" WHERE s.id=?',(sid,)).fetchone()
            if not s:raise HTTPException(404,'作业不存在')
            if s['published'] or s['returned'] or s['score'] is not None or s['feedback']:
                raise HTTPException(409,'已发布、已退回或已有教师评分草稿的作业不加入AI队列')
            if (s['ai_json'] and not replace_ai) or s['status'] in BUSY or c.execute("SELECT 1 FROM paper_review_jobs WHERE submission_id=? AND state IN ('pending','running')",(sid,)).fetchone():
                raise HTTPException(409,'作业已有AI结果或已在批改队列中')
            if c.execute("SELECT COUNT(*) FROM paper_review_jobs WHERE state IN ('pending','running')").fetchone()[0]>=500:
                raise HTTPException(409,'批改队列已满（500份），请等待部分完成')
            jid=c.execute('INSERT INTO paper_review_jobs(submission_id,path,run_at,previous_status,created) VALUES(?,?,?,?,?)',(sid,s['path'],due,s['status'],time.time())).lastrowid
            c.execute('UPDATE submissions SET status=? WHERE id=?',('AI定时待批改' if due>time.time()+1 else 'AI排队中',sid))
        if wake and due<=time.time():self.wake()
        return jid

    def wake(self):
        if self.slot.acquire(blocking=False):
            try:self.pool.submit(self._drain)
            except Exception:self.slot.release();raise

    def _drain(self):
        try:
            while not self.stop_event.is_set() and self.run_one():pass
        finally:self.slot.release()

    def run_one(self,stamp=None):
        stamp=time.time() if stamp is None else stamp
        cfg=self.settings()
        if not cfg.get('key') or not cfg.get('model'):return False
        if cfg.get('off_peak_only',False) and peak(stamp):return False
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            job=c.execute("SELECT * FROM paper_review_jobs WHERE state='pending' AND run_at<=? ORDER BY run_at,id LIMIT 1",(stamp,)).fetchone()
            if not job:return False
            s=c.execute('SELECT s.* FROM submissions s JOIN assignments a ON a.id=s.assignment_id AND a.deleted_at="" WHERE s.id=?',(job['submission_id'],)).fetchone()
            if not s or s['path']!=job['path'] or s['published'] or s['returned'] or s['score'] is not None or s['feedback']:
                c.execute("UPDATE paper_review_jobs SET state='cancelled',finished=?,error='提交已变更或已由教师处理' WHERE id=?",(stamp,job['id']))
                return True
            c.execute("UPDATE paper_review_jobs SET state='running',error='' WHERE id=?",(job['id'],))
            c.execute("UPDATE submissions SET status='AI批改中' WHERE id=?",(job['submission_id'],))
        try:
            success=self.review(job['submission_id'])
            error='' if success else 'AI未完成有效批改，请查看作业状态后手动重试'
        except DeferReview:
            with self.db() as c:
                c.execute("UPDATE paper_review_jobs SET state='pending' WHERE id=?",(job['id'],))
                c.execute("UPDATE submissions SET status='AI排队中' WHERE id=? AND path=?",(job['submission_id'],job['path']))
            return False
        except DailyQuotaExceeded as exc:
            with self.db() as c:
                c.execute("UPDATE paper_review_jobs SET state='pending',run_at=?,error=? WHERE id=?",(exc.retry_at,str(exc),job['id']))
                c.execute("UPDATE submissions SET status='AI定时待批改' WHERE id=? AND path=?",(job['submission_id'],job['path']))
            return True
        except Exception:
            success=False;error='批改任务异常，请教师查看后重试'
            with self.db() as c:c.execute("UPDATE submissions SET status='预审需人工处理：任务异常' WHERE id=? AND path=?",(job['submission_id'],job['path']))
        with self.db() as c:c.execute('UPDATE paper_review_jobs SET state=?,finished=?,error=? WHERE id=?',('completed' if success else 'failed',time.time(),error,job['id']))
        return True

    def cancel(self,jid):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            job=c.execute('SELECT * FROM paper_review_jobs WHERE id=?',(jid,)).fetchone()
            if not job:raise HTTPException(404,'任务不存在')
            if job['state']!='pending':raise HTTPException(409,'只能取消尚未开始的任务')
            c.execute("UPDATE paper_review_jobs SET state='cancelled',finished=? WHERE id=?",(time.time(),jid))
            c.execute('UPDATE submissions SET status=? WHERE id=? AND path=? AND status IN (?,?)',(job['previous_status'],job['submission_id'],job['path'],'AI排队中','AI定时待批改'))

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear()
        def tick():
            while not self.stop_event.wait(15):
                try:self.wake()
                except Exception:pass
        self.thread=threading.Thread(target=tick,daemon=True);self.thread.start();self.wake()

    def stop(self):self.stop_event.set()
