"""平台固定模型工具：只在可信本地练习或隔离评测容器内导入。"""
from pathlib import Path
from runner import load_session

# 本地与服务器均使用本场冻结的教师模型；加载发生在agent导入时，不计落子时间。
_root = Path(__file__).resolve().parent
_path = Path('/input/teacher-baseline.onnx') if Path('/input/teacher-baseline.onnx').is_file() else _root/'teacher-baseline.onnx'
_predict = load_session(_path)


def evaluate(board):
    """输入15×15列表，1自己/-1对手/0空位。
    返回(value, policy)：value在[-1,1]内，为模型对当前己方局面的估计，
    不是校准后的胜率；policy为15×15非负落子偏好，已占位置为0，
    有空位时总和约为1。一次调用仅做神经网络推理，不做搜索。
    不修改输入。固定模型不是教师完整的化神搜索算法。
    """
    if not isinstance(board,(list,tuple)) or len(board)!=15 or any(not isinstance(row,(list,tuple)) or len(row)!=15 for row in board):
        raise ValueError('evaluate需要15×15二维棋盘')
    flat=[v for row in board for v in row]
    if any(type(v) is not int or v not in (-1,0,1) for v in flat):
        raise ValueError('棋盘元素只能是整数-1、0、1')
    value, policy = _predict(flat)
    return value, [policy[i*15:(i+1)*15] for i in range(15)]
