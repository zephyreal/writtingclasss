"""Trusted arbiter on a dedicated machine. Each model lives in its own gVisor sandbox.
The arbiter never imports ONNX or executes student source code, and it alone builds game records.
"""
import argparse
import hashlib
import json
import math
import os
import platform
import queue
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from arena_engine import ENGINE,play_game


def container_command(image,folder,name,memory_mb):
    return ['docker','run','--interactive','--name',name,'--runtime=runsc','--network=none','--read-only','--cap-drop=ALL',
        '--security-opt=no-new-privileges:true','--label=course-arena-managed=1','--log-driver=none','--pids-limit=64','--memory='+str(memory_mb)+'m','--memory-swap='+str(memory_mb)+'m',
        '--cpus=1','--user=65534:65534','--tmpfs=/tmp:rw,noexec,nosuid,size=64m','--mount=type=bind,src='+str(folder)+',dst=/input,readonly',image]


def remove_container(name):
    try:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
    except (OSError,subprocess.TimeoutExpired):pass


def runtime_info(image):
    runtimes=json.loads(subprocess.check_output(['docker','info','--format','{{json .Runtimes}}'],timeout=15,text=True))
    if 'runsc' not in runtimes:raise RuntimeError('尚未安装gVisor/runsc；不允许降级为普通容器或本机推理')
    digest=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True,timeout=15).strip()
    if not digest.startswith('sha256:'):raise RuntimeError('评测镜像不可用，请先构建镜像')
    runtime_path=runtimes['runsc'].get('path','runsc') if isinstance(runtimes['runsc'],dict) else 'runsc'
    runtime_version=subprocess.check_output([runtime_path,'--version'],text=True,timeout=10).strip()
    cpu=''
    if Path('/proc/cpuinfo').exists():cpu=next((line for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),'')
    source=Path(__file__).read_bytes()+(Path(__file__).parents[1]/'arena_engine.py').read_bytes()
    fingerprint=hashlib.sha256(json.dumps({'engine':ENGINE,'arbiter':hashlib.sha256(source).hexdigest(),'image':digest,'machine':platform.machine(),'cpu':cpu,'runtime':'runsc','runtime_version':runtime_version,'kernel':platform.release()},sort_keys=True).encode()).hexdigest()
    return digest,fingerprint


class DockerAgent:
    def __init__(self,image,folder,name,memory_mb):
        self.name=name;self.messages=queue.Queue(maxsize=2);self.bad=threading.Event();self.closed=False
        self.process=subprocess.Popen(container_command(image,folder,name,memory_mb),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=65536)
        def receive():
            try:
                while True:
                    line=self.process.stdout.readline(262145)
                    if not line:break
                    if len(line)>262144:raise ValueError()
                    self.messages.put_nowait(json.loads(line))
            except Exception:self.bad.set()
            finally:
                try:self.messages.put_nowait(None)
                except queue.Full:self.bad.set()
        def stderr():
            size=0
            try:
                while chunk:=self.process.stderr.read(65536):
                    size+=len(chunk)
                    if size>2_000_000:self.bad.set();return
            except (OSError,ValueError):pass
        self.readers=[threading.Thread(target=fn,daemon=True) for fn in (receive,stderr)]
        for r in self.readers:r.start()
        try:
            message=self.next(time.monotonic()+30)
            if not isinstance(message,dict) or message.get('ready') is not True:raise ValueError('模型校验失败：'+str(message.get('error','未返回就绪信息'))[:160] if isinstance(message,dict) else '模型加载进程异常')
        except Exception:self.close();raise
    def next(self,deadline):
        if self.bad.is_set():raise ValueError('模型输出协议或日志超过限制')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError()
        try:message=self.messages.get(timeout=remaining)
        except queue.Empty:raise TimeoutError()
        if message is None:raise ValueError('模型进程中断')
        return message
    def predict(self,board,deadline):
        request_id=secrets.token_hex(12)
        request=json.dumps({'request_id':request_id,'board':board},separators=(',',':')).encode()+b'\n'
        try:self.process.stdin.write(request);self.process.stdin.flush()
        except (OSError,BrokenPipeError):raise ValueError('模型进程中断')
        reply=self.next(deadline)
        if not isinstance(reply,dict) or reply.get('request_id')!=request_id:raise ValueError('模型响应标识不匹配')
        value=reply.get('value');policy=reply.get('policy')
        if type(value) not in (int,float) or not math.isfinite(value) or not -1.00001<=value<=1.00001 or not isinstance(policy,list) or len(policy)!=225:raise ValueError('模型输出格式不正确')
        if any(type(p) not in (int,float) or not math.isfinite(p) for p in policy):raise ValueError('模型落子概率无效')
        policy=[max(0,float(p)) if board[i]==0 else 0. for i,p in enumerate(policy)];total=sum(policy)
        if not math.isfinite(total):raise ValueError('模型输出超出范围')
        if total<=0:
            policy=[float(v==0) for v in board];total=sum(policy)
        return float(value),[p/total if total else 0 for p in policy]
    def close(self):
        if self.closed:return
        self.closed=True;remove_container(self.name)
        if self.process.poll() is None:self.process.kill()
        try:self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:pass
        for pipe in (self.process.stdin,self.process.stdout,self.process.stderr):
            try:pipe.close()
            except OSError:pass
        for r in self.readers:r.join(timeout=1)


class Worker:
    def __init__(self,url,token,worker_id,image):
        parsed=urlparse(url)
        if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('评测机只连接有效HTTPS网站地址')
        self.client=httpx.Client(base_url=url.rstrip('/'),headers={'Authorization':'Bearer '+token,'X-App-Request':'1'},timeout=30,follow_redirects=False,trust_env=False)
        self.worker_id=worker_id;self.image=image;self.fingerprint='0'*64
    def request(self,path,data,timeout=30):
        r=self.client.post('/api/arena/worker/'+path,json=data,timeout=timeout);r.raise_for_status();return r.json()
    def ping(self,ready,error=''):
        return self.request('ping',{'worker_id':self.worker_id,'fingerprint':self.fingerprint,'ready':ready,'error':error[:200]})
    def download(self,job,kind,destination):
        size=0;digest=hashlib.sha256()
        with self.client.stream('GET',f"/api/arena/worker/jobs/{job['id']}/files/{kind}",headers={'X-Arena-Lease':job['lease']}) as r:
            r.raise_for_status()
            with Path(destination).open('wb') as f:
                for chunk in r.iter_bytes():
                    size+=len(chunk)
                    if size>20_000_000:raise ValueError('下载文件超过上限')
                    digest.update(chunk);f.write(chunk)
        expected=job['model_hash'] if kind=='model' else job['baseline_hash']
        if digest.hexdigest()!=expected:raise ValueError('文件校验值不一致')
    def execute(self,job,image):
        cancelled=threading.Event();done=threading.Event();budget=threading.Event();names=set();names_lock=threading.Lock()
        until=time.monotonic()+job['config']['job_seconds'];progress={'completed_games':0,'phase':'validating'}
        def terminate():
            with names_lock:active=list(names)
            for name in active:remove_container(name)
        def renew():
            failures=0
            while not done.wait(10):
                if time.monotonic()>until:budget.set();terminate();return
                try:self.request(f"jobs/{job['id']}/heartbeat",{'lease':job['lease'],**progress},timeout=8);failures=0
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (401,403,409):cancelled.set();terminate();return
                    failures+=1
                except Exception:failures+=1
                if failures>=3:cancelled.set();terminate();return
        heartbeat=threading.Thread(target=renew,daemon=True);heartbeat.start()
        try:
            with tempfile.TemporaryDirectory(prefix='arena-input-',dir=os.getenv('ARENA_WORK_DIR') or None) as tmp:
                folder=Path(tmp);folders={}
                for kind in ('student','baseline'):
                    target=folder/kind;target.mkdir(mode=0o755);self.download(job,'model' if kind=='student' else 'baseline',target/'model.onnx')
                    os.chmod(target/'model.onnx',0o444);folders[kind]=target
                def agent(kind):
                    if cancelled.is_set():raise RuntimeError('任务已取消')
                    if budget.is_set() or time.monotonic()>until:raise TimeoutError('整场资源预算已用完')
                    name='course-arena-'+self.worker_id+'-'+secrets.token_hex(8)
                    with names_lock:names.add(name)
                    try:return DockerAgent(image,folders[kind],name,job['config']['memory_mb']//2)
                    except Exception:
                        remove_container(name)
                        with names_lock:names.discard(name)
                        raise
                # Prove the known baseline starts before attributing loading errors to a student.
                probe=agent('baseline');probe.close()
                with names_lock:names.discard(probe.name)
                try:
                    probe=agent('student');probe.close()
                    with names_lock:names.discard(probe.name)
                except (ValueError,TimeoutError) as exc:
                    message=str(exc)[:220] if isinstance(exc,ValueError) and str(exc).startswith('模型校验失败：') else '模型加载/预热超时、中断或超出资源上限，请检查导出接口'
                    return {'status':'rejected','error':message,'games':[]}
                progress['phase']='playing'
                games=[]
                for n,opening in enumerate(job['openings']):
                    for color in (1,-1):
                        baseline=student=None
                        try:
                            baseline=agent('baseline');student=agent('student')
                            games.append(play_game(opening,color,student,baseline,job['config'],n*2+(0 if color==1 else 1)))
                            progress['completed_games']=len(games)
                        finally:
                            for model in (student,baseline):
                                if model:
                                    model.close()
                                    with names_lock:names.discard(model.name)
                if cancelled.is_set():return None
                if budget.is_set():return {'status':'rejected','error':'超过整次评测总时间预算','games':[]}
                return {'status':'completed','games':games,'error':''}
        except Exception:
            if cancelled.is_set():return None
            if budget.is_set() or time.monotonic()>until:return {'status':'rejected','error':'超过整次评测总时间预算','games':[]}
            return {'status':'failed','error':'隔离评测或教师基准运行异常，未生成有效成绩，请教师检查后重试','games':[]}
        finally:
            done.set();heartbeat.join(timeout=35);terminate()
    def tick(self):
        image,fingerprint=runtime_info(self.image);self.fingerprint=fingerprint;self.ping(True)
        reply=self.request('claim',{'worker_id':self.worker_id,'fingerprint':fingerprint,'ready':True})
        job=reply.get('job')
        if not job:return False
        try:result=self.execute(job,image)
        except Exception:result={'status':'failed','error':'评测机下载或执行失败，请教师检查后重试','games':[]}
        if result is not None:
            result.update(lease=job['lease'],fingerprint=fingerprint)
            try:self.request(f"jobs/{job['id']}/result",result)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (400,422):raise
                self.request(f"jobs/{job['id']}/result",{'lease':job['lease'],'fingerprint':fingerprint,'status':'failed','error':'裁判报告未通过网站一致性校验，请教师检查运行环境后重试','games':[]})
        return True


def main():
    parser=argparse.ArgumentParser(description='Independent gVisor model competition arbiter')
    parser.add_argument('--config',required=True,help='chmod 600 JSON config, never a student attachment');parser.add_argument('--once',action='store_true');args=parser.parse_args()
    file=Path(args.config)
    if file.stat().st_mode&0o077:raise SystemExit('配置文件含凭证，请先chmod 600')
    config=json.loads(file.read_text());worker=Worker(config['url'],config['token'],config.get('worker_id','course-arena-1'),config.get('image','writing-course-arena:v1'))
    # One official worker per service account; after a crash, clean only our labelled orphans.
    import fcntl
    work=Path(os.getenv('ARENA_WORK_DIR') or (Path.home()/'.cache/course-arena'));work.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=os.fdopen(os.open(work/'worker.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),'w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('本机服务账号已有评测机进程运行，请勿重复启动')
    try:
        ids=subprocess.check_output(['docker','ps','-aq','--filter','label=course-arena-managed=1','--filter','name=^/course-arena-'+worker.worker_id+'-'],text=True,timeout=15).split()
        for cid in ids:
            if len(cid)>=12 and all(ch in '0123456789abcdef' for ch in cid):remove_container(cid)
    except (OSError,subprocess.SubprocessError):pass
    while True:
        try:active=worker.tick()
        except Exception as exc:
            print('评测机未就绪或任务失败：'+type(exc).__name__,flush=True)
            try:worker.ping(False,'评测机运行库、隔离环境或连接异常，请检查Docker与gVisor')
            except Exception:pass
            active=False
        if args.once:break
        if not active:time.sleep(10)

if __name__=='__main__':main()
