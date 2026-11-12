"""Create a tiny, deterministic ONNX interface example; not a strong player."""
import argparse
from pathlib import Path
import numpy as np
import onnx
from onnx import helper,TensorProto,numpy_helper


def build(path):
    graph=helper.make_graph([
        helper.make_node('Constant',[],['value'],value=numpy_helper.from_array(np.zeros((1,1),dtype=np.float32))),
        helper.make_node('Constant',[],['policy'],value=numpy_helper.from_array(np.full((1,225),1/225,dtype=np.float32)))
    ],'interface-example',[helper.make_tensor_value_info('board',TensorProto.FLOAT,[1,3,15,15])],
    [helper.make_tensor_value_info('value',TensorProto.FLOAT,[1,1]),helper.make_tensor_value_info('policy',TensorProto.FLOAT,[1,225])])
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)],ir_version=9)
    onnx.checker.check_model(model);onnx.save(model,str(path))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='my-gomoku.onnx');args=parser.parse_args();build(Path(args.output));print('已生成接口示例：'+args.output)
