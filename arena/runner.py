"""Container-only inference runner. The production host must launch this through gVisor."""
import hashlib
import json
import math
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

from arena_engine import CELLS,ENGINE,choose,five,position


def load_session(path):
    import numpy as np
    import onnx
    import onnxruntime as ort
    if Path(path).stat().st_size>20_000_000:raise ValueError('模型超过20MB')
    model=onnx.load(path,load_external_data=False)
    if model.training_info:raise ValueError('请导出纯推理模型')
    prohibited={'RandomNormal','RandomUniform','RandomNormalLike','RandomUniformLike','Multinomial','Dropout','Bernoulli','Loop','Scan'}
    stack=[model];messages=0;elements=0
    while stack:
        message=stack.pop();messages+=1
        if messages>100000:raise ValueError('模型结构过大')
        if message.DESCRIPTOR.full_name=='onnx.NodeProto' and (message.op_type in prohibited or message.domain not in ('','ai.onnx','com.microsoft')):raise ValueError('不支持随机、循环或自定义算子，请导出确定性推理模型')
        if message.DESCRIPTOR.full_name=='onnx.TensorProto':
            if message.external_data or message.data_location==onnx.TensorProto.EXTERNAL:raise ValueError('不支持外部权重文件，请导出单文件ONNX')
            count=math.prod(message.dims) if message.dims else 1
            if count<0 or count>25_000_000:raise ValueError('模型张量超出容量限制')
            elements+=count
            if elements>30_000_000:raise ValueError('模型参数或常量总量过大')
        for field,value in message.ListFields():
            if field.type==field.TYPE_MESSAGE:
                if field.is_repeated:stack.extend(value)
                else:stack.append(value)
    prohibited={'RandomNormal','RandomUniform','RandomNormalLike','RandomUniformLike','Multinomial','Dropout','Bernoulli'}
    if any(n.op_type in prohibited for n in model.graph.node):raise ValueError('正式比赛不支持随机算子，请导出eval模式的确定性模型')
    if len(model.graph.node)>5000:raise ValueError('模型节点超过5000')
    onnx.checker.check_model(model)
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;options.enable_cpu_mem_arena=False
    options.add_session_config_entry('session.intra_op.allow_spinning','0')
    session=ort.InferenceSession(model.SerializeToString(),sess_options=options,providers=['CPUExecutionProvider'])
    inputs=session.get_inputs();outputs=session.get_outputs()
    if len(inputs)!=1 or inputs[0].name!='board' or inputs[0].type!='tensor(float)' or inputs[0].shape!=[1,3,15,15]:raise ValueError('输入必须是board: float32[1,3,15,15]')
    if {o.name for o in outputs}!={'value','policy'}:raise ValueError('输出名称必须为value和policy')
    def predict(board):
        board=np.asarray(board,dtype=np.int8).reshape(15,15)
        data=np.stack((board==1,board==-1,board==0)).astype(np.float32)[None]
        value,policy=session.run(['value','policy'],{'board':data})
        if value.size!=1 or policy.size!=225 or not np.isfinite(value).all() or not np.isfinite(policy).all():raise ValueError('输出须为有限value标量及225维policy')
        value=float(value.reshape(-1)[0])
        if not -1.00001<=value<=1.00001:raise ValueError('value须在-1至1之间')
        policy=policy.reshape(-1);legal=board.reshape(-1)==0;policy=np.where(legal,np.maximum(policy,0),0)
        total=float(policy.sum())
        if not math.isfinite(total):raise ValueError('policy无效')
        if total<=0:policy=legal.astype(np.float32);total=float(policy.sum())
        if total>0:policy=policy/total
        return value,[float(x) for x in policy]
    predict([0]*225)  # Warm-up is identical for both participants and outside move clocks.
    return predict


def model_process(path,pipe):
    try:
        predict=load_session(path);pipe.send({'ready':True})
    except Exception as exc:
        # Only fixed validation messages; never send stack traces or server paths to learners.
        safe=str(exc) if isinstance(exc,ValueError) else '模型无法加载，请检查导出格式和算子兼容性'
        pipe.send({'ready':False,'error':safe[:160]});pipe.close();return
    try:
        while True:
            board=pipe.recv()
            if board is None:break
            try:pipe.send({'prediction':predict(board)})
            except Exception:pipe.send({'error':'模型在该局面未返回有效预测'})
    except (EOFError,BrokenPipeError):pass
    finally:pipe.close()


class ModelClient:
    def __init__(self,path,load_seconds=30):
        context=mp.get_context('spawn');self.pipe,remote=context.Pipe()
        self.process=context.Process(target=model_process,args=(str(path),remote),daemon=True);self.process.start();remote.close()
        if not self.pipe.poll(load_seconds):self.close();raise ValueError('模型加载或预热超时')
        try:reply=self.pipe.recv()
        except EOFError:self.close();raise ValueError('模型加载进程中断或超出资源上限')
        if not reply.get('ready'):self.close();raise ValueError(reply.get('error','模型校验失败'))
    def predict(self,board,deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError()
        try:
            self.pipe.send(board)
            if not self.pipe.poll(remaining):raise TimeoutError()
            result=self.pipe.recv()
        except (EOFError,BrokenPipeError,OSError):raise ValueError('模型进程异常')
        if 'prediction' not in result:raise ValueError('模型未返回有效预测')
        return result['prediction']
    def close(self):
        if hasattr(self,'process') and self.process.is_alive():self.process.kill()
        if hasattr(self,'process'):self.process.join(timeout=2)
        if hasattr(self,'pipe'):self.pipe.close()


# Trusted local tests may supply their own agents; production arbitration lives outside containers.
from arena_engine import play_game as run_game

if __name__=='__main__':raise SystemExit('请通过arena/worker.py启动正式隔离评测；此模块不接收整场评测任务')
