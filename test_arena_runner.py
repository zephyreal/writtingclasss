import hashlib
import importlib.util
import json
import time
from pathlib import Path
import pytest
from arena.worker import container_command,Worker
from arena_engine import choose,openings,verify_games


def test_worker_always_requires_hardened_container_and_private_token():
    command=container_command('sha256:trusted',Path('/tmp/input'),'arena-test',1024)
    for required in ['--runtime=runsc','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges:true','--pids-limit=64','--cpus=1','--user=65534:65534','--log-driver=none']:assert required in command
    assert not any('token' in x or 'docker.sock' in x for x in command)
    assert command[-1]=='sha256:trusted' and any('dst=/input,readonly' in x for x in command)
    with pytest.raises(ValueError):Worker('http://example.com','private-key','node','image')


@pytest.mark.skipif(importlib.util.find_spec('onnxruntime') is None,reason='独立评测机推理依赖未安装')
def test_trusted_bundled_baseline_real_inference_and_example(tmp_path):
    from arena.runner import ModelClient,load_session,run_game
    from arena.example_model import build
    example=tmp_path/'example.onnx';build(example)
    constant=load_session(example);value,policy=constant([0]*225)
    assert value==0 and len(policy)==225 and sum(policy)==pytest.approx(1)
    baseline=Path(__file__).parent/'course_assets/gomoku/gomoku_uint8_qop_u8u8.onnx'
    one=two=None
    try:
        one=ModelClient(baseline);two=ModelClient(baseline)
        value,policy=one.predict([0]*225,time.monotonic()+3)
        assert -1<=value<=1 and len(policy)==225 and sum(policy)==pytest.approx(1)
        opening=openings('trusted-smoke',1)[0];cfg={'simulations':2,'move_ms':3000}
        games=[run_game(opening,color,one,two,cfg,i) for i,color in enumerate((1,-1))]
        result=verify_games([opening],games,3000)
        assert result['games']==2 and result['score']==50
    finally:
        if one:one.close()
        if two:two.close()


@pytest.mark.skipif(importlib.util.find_spec('onnx') is None,reason='独立评测机模型检查依赖未安装')
def test_external_data_and_random_operators_are_rejected(tmp_path):
    import onnx
    from onnx import helper,TensorProto
    from arena.runner import load_session
    tensor=helper.make_tensor('secret',TensorProto.FLOAT,[1],[1.])
    tensor.ClearField('float_data');tensor.data_location=TensorProto.EXTERNAL
    item=tensor.external_data.add();item.key='location';item.value='/etc/passwd'
    graph=helper.make_graph([], 'external',[],[],[tensor])
    path=tmp_path/'external.onnx';path.write_bytes(helper.make_model(graph).SerializeToString())
    with pytest.raises(ValueError,match='外部权重'):load_session(path)
    graph=helper.make_graph([helper.make_node('RandomUniform',[],['policy'],shape=[1,225])],'random',[],[helper.make_tensor_value_info('policy',TensorProto.FLOAT,[1,225])])
    path=tmp_path/'random.onnx';path.write_bytes(helper.make_model(graph).SerializeToString())
    with pytest.raises(ValueError,match='随机'):load_session(path)


@pytest.mark.skipif(importlib.util.find_spec('onnxruntime') is None,reason='独立评测机推理依赖未安装')
def test_numpy_training_template_exports_valid_model(tmp_path):
    from arena.train_example import train
    from arena.runner import load_session
    baseline=Path(__file__).parent/'course_assets/gomoku/gomoku_uint8_qop_u8u8.onnx'
    output=tmp_path/'trained.onnx';train(baseline,output,samples=16,epochs=1)
    value,policy=load_session(output)([0]*225)
    assert len(policy)==225 and sum(policy)==pytest.approx(1) and -1<=value<=1


def test_no_fallback_when_gvisor_is_not_installed(monkeypatch):
    from arena.worker import runtime_info
    monkeypatch.setattr('arena.worker.subprocess.check_output',lambda *args,**kw:'{"runc": {"path":"runc"}}')
    with pytest.raises(RuntimeError,match='runsc'):runtime_info('image')


def test_trusted_arbiter_never_mounts_both_models_or_game_manifest(tmp_path,monkeypatch):
    from arena.worker import Worker
    from arena_engine import ENGINE
    seen=[]
    class FakeSandbox:
        def __init__(self,image,folder,name,memory_mb):
            assert image=='frozen-image' and memory_mb==512
            assert [p.name for p in folder.iterdir()]==['model.onnx']
            seen.append(folder.name);self.name=name
        def predict(self,board,deadline):return 0,[1/225]*225
        def close(self):pass
    monkeypatch.setattr('arena.worker.DockerAgent',FakeSandbox)
    monkeypatch.setattr('arena.worker.remove_container',lambda name:None)
    worker=Worker('https://course.example','never-mounted-secret','node','image')
    monkeypatch.setattr(worker,'download',lambda job,kind,path:Path(path).write_bytes(kind.encode()))
    monkeypatch.setattr(worker,'request',lambda *args,**kw:{'ok':True})
    bank=openings('arbiter-isolation',1)
    result=worker.execute({'id':1,'lease':'private-lease','config':{'engine':ENGINE,'simulations':2,'move_ms':5000,'job_seconds':60,'memory_mb':1024},'openings':bank},'frozen-image')
    assert result['status']=='completed' and verify_games(bank,result['games'],5000)['score']==50
    assert seen.count('student')==seen.count('baseline') and 'student' in seen
