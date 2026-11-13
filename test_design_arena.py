import copy
import importlib.util
import io
import json
import sqlite3
import time
import zipfile
from pathlib import Path
import pytest
from test_app import a,student,teacher,client,H
from arena_engine import five,position,openings,verify_games,choose

@pytest.fixture
def setup(tmp_path,monkeypatch):
    with sqlite3.connect(a.DB) as source,sqlite3.connect(tmp_path/'arena.db') as dest:source.backup(dest)
    monkeypatch.setattr(a,'DB',tmp_path/'arena.db');a.init()
    t=teacher();s=student('arena-student');other=student('arena-other')
    worker=client();r=t.post('/api/arena/admin/worker',json={'worker_id':'arena-node-1'});assert r.status_code==200
    worker.headers['Authorization']='Bearer '+r.json()['token']
    return t,s,other,worker


def competition(t,legacy=True,**changes):
    body={'title':'模型比赛','pairs':1,'simulations':2,'daily_limit':5};body.update(changes)
    r=t.post('/api/arena/admin/competitions',json=body);assert r.status_code==200,r.text
    cid=r.json()['id']
    if legacy:
        # Existing suites exercise frozen, pre-function model competitions.
        with a.db() as db:
            cfg=json.loads(db.execute('SELECT config FROM arena_competitions WHERE id=?',(cid,)).fetchone()[0]);cfg.pop('submission',None)
            db.execute('UPDATE arena_competitions SET config=? WHERE id=?',(json.dumps(cfg),cid))
    return cid


def submit(s,cid,**changes):
    body={'alias':'学生 <script>','note':'首次参赛','share_replay':'false'};body.update(changes)
    return s.post(f'/api/arena/competitions/{cid}/entries',data=body,files={'model':('my.onnx',b'opaque-not-parsed-by-web')})


def claim(w,fingerprint='a'*64):
    r=w.post('/api/arena/worker/claim',json={'worker_id':'arena-node-1','fingerprint':fingerprint,'ready':True});assert r.status_code==200,r.text
    return r.json()['job']


def forfeits(job):
    games=[]
    for n,opening in enumerate(job['openings']):
        for color in (1,-1):
            moves=opening[:];times=[]
            if color==-1:
                move=next(i for i in range(225) if i not in moves);moves.append(move);times=[1.0]
            games.append({'index':len(games),'student_color':color,'moves':moves,'times_ms':times,'fault':'student_timeout'})
    return {'lease':job['lease'],'fingerprint':job['fingerprint'],'status':'completed','games':games,'score':99999}


def finish(w,job):
    r=w.post(f"/api/arena/worker/jobs/{job['id']}/result",json=forfeits(job));assert r.status_code==200,r.text


def test_rules_openings_and_deterministic_search():
    bank=openings('fixed',20);assert bank==openings('fixed',20) and len({tuple(x) for x in bank})==20
    for seq in bank:assert position(seq)[1]==0 and len(seq)%2==0
    b=[0]*225
    for i in range(6):b[30+i]=1
    assert five(b,35,1)  # Overlines count as a win, exactly as the teaching game.
    with pytest.raises(ValueError):position([1,1])
    b=[0]*225
    for i in range(4):b[30+i]=1
    move=choose(b,1,lambda board,deadline:(0,[1/225]*225),2,time.monotonic()+2)
    assert move==34
    empty=[0]*225;predict=lambda board,deadline:(0,[1/225]*225)
    assert choose(empty,1,predict,4,time.monotonic()+2)==choose(empty,1,predict,4,time.monotonic()+2)


def test_upload_permissions_private_files_and_worker_scope(setup):
    t,s,other,w=setup;cid=competition(t)
    with a.db() as c:
        uid=other.get('/api/me').json()['id'];c.execute("UPDATE course_memberships SET active=0 WHERE user_id=? AND course_id='design'",(uid,))
    assert other.get('/api/arena/competitions').status_code==403
    assert submit(other,cid).status_code==403
    assert s.post('/api/arena/admin/competitions',json={'title':'越权'}).status_code==403
    r=submit(s,cid);assert r.status_code==200;eid=r.json()['id']
    assert r.json()['state']=='pending'
    assert s.get(f'/api/arena/entries/{eid}/files/model').content==b'opaque-not-parsed-by-web'
    outsider=student('arena-outsider')
    assert outsider.get(f'/api/arena/entries/{eid}/files/model').status_code==404
    assert t.get(f'/api/arena/entries/{eid}/files/model').status_code==200
    assert w.get('/api/teacher/students').status_code==401
    assert client().post('/api/arena/worker/claim',json={'worker_id':'arena-node-1','fingerprint':'a'*64}).status_code==401
    status=s.get('/api/arena/competitions').json()
    assert 'token_hash' not in json.dumps(status) and 'openings' not in json.dumps(status)
    job=claim(w);assert job['id']==eid
    assert claim(w) is None
    assert w.get(f'/api/arena/worker/jobs/{eid}/files/model',headers={'X-Arena-Lease':job['lease']}).content==b'opaque-not-parsed-by-web'
    assert w.get(f'/api/arena/worker/jobs/{eid}/files/model',headers={'X-Arena-Lease':'wrong'}).status_code==409


def test_server_replays_report_and_computes_score(setup):
    t,s,other,w=setup;cid=competition(t);eid=submit(s,cid).json()['id'];job=claim(w)
    report=forfeits(job);bad=copy.deepcopy(report);bad['games'][0]['moves']=[0]
    assert w.post(f'/api/arena/worker/jobs/{eid}/result',json=bad).status_code==400
    missing=copy.deepcopy(report);missing['games']=missing['games'][:1]
    assert w.post(f'/api/arena/worker/jobs/{eid}/result',json=missing).status_code==400
    assert s.post(f'/api/arena/worker/jobs/{eid}/result',json=report).status_code==401
    finish(w,job)
    board=s.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows']
    assert board[0]['score']==0 and board[0]['losses']==2 and board[0]['rank']==1
    assert 'student_no' not in board[0]
    assert s.get(f'/api/arena/entries/{eid}/replay').status_code==200
    assert other.get(f'/api/arena/entries/{eid}/replay').status_code==403
    assert w.post(f'/api/arena/worker/jobs/{eid}/result',json=report).status_code==409


def test_latest_versions_ties_and_teacher_disqualification(setup):
    t,s,other,w=setup;cid=competition(t)
    one=submit(s,cid,share_replay='true').json()['id'];finish(w,claim(w))
    assert other.get(f'/api/arena/entries/{one}/replay').status_code==200
    two=submit(other,cid).json()['id'];finish(w,claim(w))
    board=s.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows'];assert [r['rank'] for r in board]==[1,1]
    pending=submit(s,cid).json()['id']
    assert one in {r['entry_id'] for r in s.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows']}
    finish(w,claim(w))
    assert pending in {r['entry_id'] for r in s.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows']}
    assert t.post(f'/api/arena/admin/entries/{pending}/exclude',json={'reason':'提交内容需教师核查'}).status_code==200
    assert [r['entry_id'] for r in s.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows']]==[two]
    assert s.post(f'/api/arena/entries/{one}/withdraw').status_code==409


def test_final_latest_submission_sealed_until_teacher_publication(setup):
    t,s,other,w=setup;cid=competition(t,mode='final',deadline='2099-01-01T00:00')
    old=submit(s,cid).json()['id'];latest=submit(s,cid,share_replay='true').json()['id']
    assert claim(w) is None
    assert t.put(f'/api/arena/admin/competitions/{cid}',json={'published':True}).status_code==409
    assert t.put(f'/api/arena/admin/competitions/{cid}',json={'state':'closed'}).status_code==200
    job=claim(w);assert job['id']==latest;finish(w,job)
    records=s.get(f'/api/arena/competitions/{cid}/entries').json()['entries']
    assert records[0]['state']=='completed' and records[0]['result'] is None and records[0]['sealed']
    assert next(e for e in records if e['id']==old)['state']=='superseded'
    assert s.get(f'/api/arena/competitions/{cid}/leaderboard').json()=={'sealed':True,'rows':[]}
    assert s.get(f'/api/arena/entries/{latest}/replay').status_code==403
    assert t.get(f'/api/arena/entries/{latest}/replay').status_code==200
    assert t.put(f'/api/arena/admin/competitions/{cid}',json={'published':True}).status_code==200
    assert s.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows'][0]['score']==0
    assert other.get(f'/api/arena/entries/{latest}/replay').status_code==200
    assert t.put(f'/api/arena/admin/competitions/{cid}',json={'state':'open'}).status_code==409
    assert submit(s,cid).status_code==409


def test_daily_limits_expired_leases_retry_and_key_rotation(setup):
    t,s,other,w=setup;cid=competition(t,daily_limit=1)
    eid=submit(s,cid).json()['id'];assert submit(s,cid).status_code==429
    job=claim(w)
    with a.db() as c:c.execute('UPDATE arena_entries SET lease_until=? WHERE id=?',(time.time()-1,eid))
    assert claim(w) is None
    assert s.get(f'/api/arena/competitions/{cid}/entries').json()['entries'][0]['state']=='interrupted'
    assert t.post(f'/api/arena/admin/entries/{eid}/retry',json={'reason':'网络恢复后重试'}).status_code==200
    newer=claim(w);assert newer['lease']!=job['lease']
    assert w.post(f'/api/arena/worker/jobs/{eid}/result',json=forfeits(job)).status_code==409
    assert t.post('/api/arena/admin/worker',json={'worker_id':'arena-node-1'}).status_code==200
    assert w.post(f'/api/arena/worker/jobs/{eid}/heartbeat',json={'lease':newer['lease']}).status_code==401


def test_frozen_environment_and_account_deletion_cancel_jobs(setup):
    t,s,other,w=setup;cid=competition(t);eid=submit(s,cid,share_replay='true').json()['id'];job=claim(w)
    finish(w,job)
    assert other.get(f'/api/arena/entries/{eid}/replay').status_code==200
    second=submit(s,cid).json()['id'];assert claim(w,'b'*64) is None
    assert '环境' in t.get('/api/arena/competitions').json()['worker']['message']
    job=claim(w);assert job['id']==second
    uid=s.get('/api/me').json()['id']
    assert t.request('DELETE',f'/api/teacher/students/{uid}',json={'student_no':'arena-student','reason':'重复注册账号'}).status_code==200
    assert w.post(f'/api/arena/worker/jobs/{second}/heartbeat',json={'lease':job['lease']}).status_code==409
    assert other.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows']==[]
    assert other.get(f'/api/arena/entries/{eid}/replay').status_code==403
    assert t.get(f'/api/arena/entries/{eid}/replay').status_code==200


def test_source_zip_is_private_archive_and_path_checks(setup):
    t,s,other,w=setup;cid=competition(t)
    def archive(name):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr(name,'print("student code is never run")')
        return b.getvalue()
    endpoint=f'/api/arena/competitions/{cid}/entries'
    bad=s.post(endpoint,data={'alias':'test'},files={'model':('m.onnx',b'model'),'source':('s.zip',archive('../escape.py'))})
    assert bad.status_code==400
    good=s.post(endpoint,data={'alias':'test'},files={'model':('m.onnx',b'model'),'source':('s.zip',archive('agent.py'))})
    assert good.status_code==200;eid=good.json()['id']
    assert s.get(f'/api/arena/entries/{eid}/files/source').status_code==200
    assert other.get(f'/api/arena/entries/{eid}/files/source').status_code==404
    assert t.get(f'/api/arena/entries/{eid}/files/source').status_code==200
    assert s.post(endpoint,data={'alias':'test'},files={'model':('m.pth',b'pickle')}).status_code==400


def test_model_size_boundary_and_original_paper_limit(setup):
    t,s,other,w=setup;cid=competition(t)
    assert a.LIMIT==3_000_000
    r=s.post(f'/api/arena/competitions/{cid}/entries',data={'alias':'边界'},files={'model':('m.onnx',b'x'*20_000_000)})
    assert r.status_code==200
    r=s.post(f'/api/arena/competitions/{cid}/entries',data={'alias':'超大'},files={'model':('m.onnx',b'x'*20_000_001)})
    assert r.status_code==413 and '20 MB' in r.json()['detail']


def test_starter_template_and_replay_consent_can_be_revoked(setup):
    t,s,other,w=setup;cid=competition(t);eid=submit(s,cid).json()['id'];finish(w,claim(w))
    response=s.get(f'/api/arena/competitions/{cid}/starter');assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert 'arena/train_example.py' in z.namelist() and 'teacher-baseline.onnx' in z.namelist()
        assert 'arena/worker.py' not in z.namelist()
        settings=json.loads(z.read('competition.json'));assert 'openings' not in settings
    assert other.get(f'/api/arena/entries/{eid}/replay').status_code==403
    assert s.put(f'/api/arena/entries/{eid}/sharing',json={'share_replay':True}).status_code==200
    assert other.get(f'/api/arena/entries/{eid}/replay').status_code==200
    assert s.put(f'/api/arena/entries/{eid}/sharing',json={'share_replay':False}).status_code==200
    assert other.get(f'/api/arena/entries/{eid}/replay').status_code==403
    assert other.put(f'/api/arena/entries/{eid}/sharing',json={'share_replay':True}).status_code==404


def test_worker_payload_is_bounded_before_json_parsing(setup):
    t,s,other,w=setup
    assert w.post('/api/arena/worker/claim',content=b'x'*2_000_001,headers={'Content-Type':'application/json'}).status_code==413
    assert w.post('/api/arena/worker/claim',content=b'x',headers={'Content-Type':'application/octet-stream'}).status_code==415


def test_progress_is_monotonic_and_never_counts_as_a_score(setup):
    t,s,other,w=setup;cid=competition(t);eid=submit(s,cid).json()['id'];job=claim(w)
    row=s.get(f'/api/arena/competitions/{cid}/entries').json()['entries'][0]
    assert row['phase']=='validating' and row['completed_games']==0 and row['total_games']==2
    endpoint=f'/api/arena/worker/jobs/{eid}/heartbeat'
    assert w.post(endpoint,json={'lease':job['lease'],'phase':'playing','completed_games':1}).status_code==200
    row=s.get(f'/api/arena/competitions/{cid}/entries').json()['entries'][0]
    assert row['phase']=='playing' and row['completed_games']==1 and row['result'] is None
    assert not s.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows']
    assert w.post(endpoint,json={'lease':job['lease'],'completed_games':0}).status_code==400
    assert w.post(endpoint,json={'lease':job['lease'],'completed_games':3}).status_code==400
    assert w.post(endpoint,json={'lease':job['lease'],'phase':'validating'}).status_code==400
    finish(w,job)
    row=s.get(f'/api/arena/competitions/{cid}/entries').json()['entries'][0]
    assert row['phase']=='finished' and row['completed_games']==2 and row['result']['score']==0


@pytest.mark.skipif(importlib.util.find_spec('onnxruntime') is None,reason='真实教师模型联调需要独立评测机推理依赖')
@pytest.mark.parametrize('opponent',['shared','deity'])
def test_real_baseline_upload_worker_http_and_ranking_roundtrip(setup,monkeypatch,opponent):
    import hashlib
    import httpx
    from arena.runner import ModelClient
    from arena.worker import Worker
    t,s,other,registered_worker=setup
    cid=competition(t,opponent=opponent,simulations=150 if opponent=='deity' else 2,move_ms=5000,job_seconds=600)
    baseline=Path(a.ROOT)/'course_assets/gomoku/gomoku_uint8_qop_u8u8.onnx'
    expected_hash=hashlib.sha256(baseline.read_bytes()).hexdigest()
    response=s.post(f'/api/arena/competitions/{cid}/entries',data={'alias':'真实基准自测'},files={'model':('baseline-copy.onnx',baseline.read_bytes())})
    assert response.status_code==200;eid=response.json()['id']
    # Only the sandbox boundary is substituted, and only the known bundled teacher bytes may load.
    # This verifies HTTP leases, artifact transfer, inference, game records, result admission and ranking;
    # it deliberately does NOT claim to validate Docker/gVisor isolation.
    class TrustedBaselineAdapter:
        def __init__(self,image,folder,name,memory_mb,deity=False,deity_sha=''):
            from arena.deity import DeityClient
            self.deity=DeityClient(Path(a.ROOT)/'course_assets/gomoku/ai-worker.js') if deity else None
            if deity:assert deity_sha==hashlib.sha256((Path(a.ROOT)/'course_assets/gomoku/ai-worker.js').read_bytes()).hexdigest()
            assert hashlib.sha256((folder/'model.onnx').read_bytes()).hexdigest()==expected_hash
            assert memory_mb==512;self.name=name;self.native=ModelClient(folder/'model.onnx')
        def predict(self,board,deadline):return self.native.predict(board,deadline)
        def choose(self,board,deadline):return self.deity.choose(board,lambda b:self.native.predict(b,deadline),deadline)['move']
        def close(self):
            self.native.close()
            if self.deity:self.deity.close()
    monkeypatch.setattr('arena.worker.DockerAgent',TrustedBaselineAdapter)
    monkeypatch.setattr('arena.worker.remove_container',lambda name:None)
    monkeypatch.setattr('arena.worker.runtime_info',lambda image:('trusted-fixture-image','c'*64))
    outgoing=[]
    def bridge(request):
        assert request.headers['Authorization']==registered_worker.headers['Authorization']
        assert 'cookie' not in request.headers
        outgoing.append((request.method,request.url.path))
        response=registered_worker.request(request.method,request.url.path,content=request.content,headers=dict(request.headers))
        return httpx.Response(response.status_code,content=response.content,headers=response.headers)
    evaluator=Worker('https://course.example','fixture-token','arena-node-1','fixture-image');evaluator.client.close()
    evaluator.client=httpx.Client(base_url='https://course.example',headers={'Authorization':registered_worker.headers['Authorization'],'X-App-Request':'1'},transport=httpx.MockTransport(bridge),trust_env=False)
    try:assert evaluator.tick() is True
    finally:evaluator.client.close()
    records=s.get(f'/api/arena/competitions/{cid}/entries').json()['entries']
    assert records[0]['state']=='completed' and records[0]['model_hash']==expected_hash
    assert records[0]['result']['games']==2 and 0<=records[0]['result']['score']<=100
    if opponent=='shared':assert records[0]['result']['score']==50
    board=s.get(f'/api/arena/competitions/{cid}/leaderboard').json()['rows']
    assert board[0]['entry_id']==eid and board[0]['score']==records[0]['result']['score'] and board[0]['rank']==1
    games=s.get(f'/api/arena/entries/{eid}/replay').json()['games']
    assert len(games)==2 and {g['student_color'] for g in games}=={-1,1}
    assert all(not g['fault'] for g in games)
    assert sum(path.endswith('/files/model') for method,path in outgoing)==1
    assert sum(path.endswith('/files/baseline') for method,path in outgoing)==1
    assert any(path.endswith('/result') for method,path in outgoing)


def test_reports_private_escaped_and_replay_totals(setup):
    t,s,other,w=setup;cid=competition(t,title='比赛 <script>')
    eid=submit(s,cid,note='<img src=x onerror=alert(1)>',share_replay='true').json()['id']
    url=f'/api/arena/entries/{eid}/report'
    assert s.get(url).status_code==409
    finish(w,claim(w))
    report=s.get(url)
    assert report.status_code==200 and 'attachment;' in report.headers['content-disposition']
    assert report.headers['cache-control']=='no-store' and 'sandbox' in report.headers['content-security-policy']
    assert '&lt;script&gt;' in report.text and '<script>' not in report.text and '<img ' not in report.text
    payload=s.get(url+'?format=json').json()
    assert payload['schema']=='arena-report-v1' and payload['entry']['result']['score']==0
    assert sum(c['games'] for c in payload['colors'])==2 and sum(c['faults'] for c in payload['colors'])==2
    assert len(payload['replays'])==2 and len(payload['entry']['model_hash'])==64
    assert other.get(url).status_code==404  # Shared replay consent does not share private reports or notes.
    assert other.get(url+'?format=json').status_code==404
    assert t.get(url).status_code==200
    assert t.post(f'/api/arena/admin/entries/{eid}/exclude',json={'reason':'教师撤销示例'}).status_code==200
    assert '成绩已撤销' in s.get(url).text


def test_sealed_reports_and_teacher_csv_export(setup):
    import csv
    t,s,other,w=setup;cid=competition(t,mode='final',deadline='2099-01-01T00:00')
    eid=submit(s,cid,alias='=HYPERLINK("x")',note=' \t+danger').json()['id']
    t.put(f'/api/arena/admin/competitions/{cid}',json={'state':'closed'})
    finish(w,claim(w));url=f'/api/arena/entries/{eid}/report'
    assert s.get(url).status_code==403 and s.get(url+'?format=json').status_code==403
    assert t.get(url).status_code==200
    export=f'/api/arena/admin/competitions/{cid}/export'
    assert s.get(export).status_code==403
    response=t.get(export);assert response.status_code==200 and response.content.startswith(b'\xef\xbb\xbf')
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[1][4].startswith("'=HYPERLINK") and rows[1][14].startswith("'+danger")
    assert rows[1][6:8]==['1','0.0'] or rows[1][6:8]==['1','0']
    assert t.put(f'/api/arena/admin/competitions/{cid}',json={'published':True}).status_code==200
    assert s.get(url).status_code==200
    assert t.put(f'/api/arena/admin/competitions/{cid}',json={'published':False}).status_code==200
    assert s.get(url).status_code==403


def test_quota_counts_saved_versions_not_withdrawals_or_other_students(setup):
    t,s,other,w=setup;cid=competition(t,daily_limit=2)
    endpoint=f'/api/arena/competitions/{cid}/entries'
    assert s.get(endpoint).json()['quota']=={'used':0,'limit':2,'remaining':2,'timezone':'Asia/Shanghai'}
    eid=submit(s,cid).json()['id'];submit(other,cid)
    assert s.post(f'/api/arena/entries/{eid}/withdraw').status_code==200
    assert s.get(endpoint).json()['quota']['remaining']==1
    submit(s,cid);assert s.get(endpoint).json()['quota']['remaining']==0
    assert submit(s,cid).status_code==429
    assert t.get(endpoint).json()['quota'] is None
    with a.db() as c:
        c.execute('UPDATE arena_entries SET created_ts=? WHERE competition_id=?',(time.time()-86400*2,cid))
    assert s.get(endpoint).json()['quota']['remaining']==2


def test_deity_is_frozen_and_old_workers_cannot_claim_it(setup):
    from arena_engine import DEITY_ENGINE,ENGINE
    import hashlib
    t,s,other,w=setup
    invalid=t.post('/api/arena/admin/competitions',json={'title':'化神赛','opponent':'deity','simulations':16})
    assert invalid.status_code==400
    cid=competition(t,opponent='deity',simulations=150,move_ms=5000)
    cfg=s.get(f'/api/arena/competitions/{cid}/entries').json()['competition']['config']
    sha=hashlib.sha256((Path(a.ROOT)/'course_assets/gomoku/ai-worker.js').read_bytes()).hexdigest()
    assert cfg['engine']==DEITY_ENGINE and cfg['deity_sha']==sha
    eid=submit(s,cid).json()['id']
    assert claim(w) is None
    body={'worker_id':'arena-node-1','fingerprint':'a'*64,'engines':[ENGINE,DEITY_ENGINE],'deity_sha':'b'*64}
    assert w.post('/api/arena/worker/claim',json=body).json()['job'] is None
    body['deity_sha']=sha;job=w.post('/api/arena/worker/claim',json=body).json()['job'];assert job['id']==eid
    finish(w,job)
    report=s.get(f'/api/arena/entries/{eid}/report?format=json').json()
    assert report['engine']==DEITY_ENGINE and report['competition']['config']['deity_sha']==sha
    assert '严格VCF' in s.get(f'/api/arena/entries/{eid}/report').text
    t.put(f'/api/arena/admin/competitions/{cid}',json={'opponent':'shared','engine':ENGINE})
    assert s.get(f'/api/arena/competitions/{cid}/entries').json()['competition']['config']==cfg

def test_shared_compute_slot_blocks_gomoku(setup):
    t,s,other,w=setup;cid=competition(t);submit(s,cid)
    with a.db() as c:
        c.execute('CREATE TABLE vehicle_entries(state TEXT,lease_until REAL)')
        c.execute('INSERT INTO vehicle_entries VALUES(?,?)',('running',time.time()+90))
    assert claim(w) is None
    with a.db() as c:c.execute('UPDATE vehicle_entries SET lease_until=0')
    assert claim(w) is not None

def test_local_starter_trains_in_extracted_directory(setup,tmp_path):
    import subprocess,sys,os
    t,s,other,w=setup;cid=competition(t)
    response=s.get(f'/api/arena/competitions/{cid}/starter')
    target=tmp_path/'student';target.mkdir()
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert {'01_setup.bat','02_train.bat','03_check.bat','arena/student_workflow.py'}<=set(z.namelist())
        z.extractall(target)
    (target/'arena/training_config.json').write_text('{"samples":16,"epochs":1,"seed":42}')
    run=subprocess.run([sys.executable,'-m','arena.student_workflow'],cwd=target,capture_output=True,text=True,timeout=60,env={**os.environ,'OPENBLAS_NUM_THREADS':'1'})
    assert run.returncode==0,run.stdout+run.stderr
    assert (target/'output/my_model.onnx').is_file()
