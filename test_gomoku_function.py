import io,json,zipfile,time,subprocess,sys
from pathlib import Path
import pytest
from arena.function_agent import FunctionAgent
from arena_engine import play_game,position
from test_design_arena import setup,competition


def test_single_file_upload_and_capability(setup):
    t,s,other,w=setup;cid=competition(t,legacy=False)
    url=f'/api/arena/competitions/{cid}/entries'
    for name,body in [('a.zip',b'bad'),('agent.py',b'def choose_move():pass'),('a.onnx',b'bad')]:
        assert s.post(url,files={'model':(name,body)}).status_code==400
    code=b'raise RuntimeError("must not execute on website")\ndef choose_move(board): return 7,7'
    response=s.post(url,files={'model':('agent.py',code)});assert response.status_code==200,response.text
    payload={'worker_id':'arena-node-1','fingerprint':'a'*64,'ready':True}
    assert w.post('/api/arena/worker/claim',json=payload).json()['job'] is None
    payload['function_v1']=True
    job=w.post('/api/arena/worker/claim',json=payload).json()['job']
    assert job['config']['submission']=='function-v1'
    assert w.get(f"/api/arena/worker/jobs/{job['id']}/files/model",headers={'X-Arena-Lease':job['lease']}).content==code


def test_example_wins_blocks_and_checks_output(tmp_path):
    agent=FunctionAgent(Path('arena/agent.py'))
    assert agent.move([0]*225)==112
    for color in (1,-1):
        board=[0]*225
        for c in range(4):board[7*15+c]=color
        assert agent.move(board)==7*15+4
    for result in ['(True,7)','(15,0)','(7,)','(7,7)']:
        path=tmp_path/'agent.py';path.write_text('def choose_move(board): return '+result)
        board=[0]*225;board[112]=1
        with pytest.raises(ValueError):FunctionAgent(path).move(board)


def test_function_route_and_downloaded_local_run(setup,tmp_path):
    t,s,_,_=setup;cid=competition(t,legacy=False)
    response=s.get(f'/api/arena/competitions/{cid}/starter')
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert 'agent.py' in z.namelist() and 'START.bat' in z.namelist()
        assert not any(n.endswith('.onnx') for n in z.namelist())
        z.extractall(tmp_path)
    run=subprocess.run([sys.executable,'local_function_test.py'],cwd=tmp_path,capture_output=True,text=True,timeout=30,env={**__import__('os').environ,'BROWSER':'true'})
    assert run.returncode==0,run.stderr
    assert (tmp_path/'output/report.html').is_file()
    class Student:
        def choose(self,board,deadline):raise ValueError('invalid')
        def predict(self,*args):raise AssertionError('must not use MCTS')
    game=play_game([],1,Student(),None,{'submission':'function-v1','move_ms':100,'simulations':2},0)
    assert game['fault']=='student_error'
