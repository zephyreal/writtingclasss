"""Small CPU imitation-learning example, using the teacher's policy/value as labels.
This demonstrates training and export, not a claim to outperform the teacher.
"""
import argparse
import numpy as np
import onnx
from onnx import helper,TensorProto,numpy_helper
from arena.runner import load_session
from arena_engine import position


def train(teacher,output,samples=256,epochs=5,seed=42):
    rng=np.random.default_rng(seed);predict=load_session(teacher);xs=[];ps=[];vs=[]
    while len(xs)<samples:
        length=int(rng.integers(0,35));moves=[int(i) for i in rng.choice(225,length,replace=False)]
        try:board,winner=position(moves)
        except ValueError:continue
        if winner:continue
        turn=1 if length%2==0 else -1;b=np.asarray(board,dtype=np.int8)*turn
        value,policy=predict([int(v) for v in b])
        xs.append(np.stack((b==1,b==-1,b==0)).astype(np.float32).reshape(-1));ps.append(policy);vs.append([value])
    x=np.asarray(xs,dtype=np.float32);target_p=np.asarray(ps,dtype=np.float32);target_v=np.asarray(vs,dtype=np.float32)
    pw=rng.normal(0,.01,(675,225)).astype(np.float32);pb=np.zeros(225,dtype=np.float32)
    vw=rng.normal(0,.01,(675,1)).astype(np.float32);vb=np.zeros(1,dtype=np.float32)
    for epoch in range(epochs):
        for ids in np.array_split(rng.permutation(samples),max(1,(samples+31)//32)):
            batch=x[ids];logits=batch@pw+pb;logits-=logits.max(axis=1,keepdims=True)
            policy=np.exp(logits);policy/=policy.sum(axis=1,keepdims=True)
            value=np.tanh(batch@vw+vb);dp=(policy-target_p[ids])/len(ids);dv=2*(value-target_v[ids])*(1-value*value)/len(ids)
            rate=.03;pw-=rate*(batch.T@dp);pb-=rate*dp.sum(axis=0);vw-=rate*(batch.T@dv);vb-=rate*dv.sum(axis=0)
        print('训练轮次',epoch+1,'/',epochs,flush=True)
    nodes=[helper.make_node('Flatten',['board'],['flat'],axis=1),helper.make_node('MatMul',['flat','pw'],['pl']),helper.make_node('Add',['pl','pb'],['logits']),helper.make_node('Softmax',['logits'],['policy'],axis=1),helper.make_node('MatMul',['flat','vw'],['vl']),helper.make_node('Add',['vl','vb'],['value_raw']),helper.make_node('Tanh',['value_raw'],['value'])]
    graph=helper.make_graph(nodes,'student-imitation',[helper.make_tensor_value_info('board',TensorProto.FLOAT,[1,3,15,15])],[helper.make_tensor_value_info('value',TensorProto.FLOAT,[1,1]),helper.make_tensor_value_info('policy',TensorProto.FLOAT,[1,225])],[numpy_helper.from_array(v,k) for k,v in [('pw',pw),('pb',pb),('vw',vw),('vb',vb)]])
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)],ir_version=9);onnx.checker.check_model(model);onnx.save(model,str(output))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--teacher',default='teacher-baseline.onnx');parser.add_argument('--output',default='my-trained.onnx');parser.add_argument('--samples',type=int,default=256);parser.add_argument('--epochs',type=int,default=5);args=parser.parse_args()
    if not 16<=args.samples<=100000 or not 1<=args.epochs<=1000:raise SystemExit('samples须16—100000，epochs须1—1000')
    train(args.teacher,args.output,args.samples,args.epochs)
