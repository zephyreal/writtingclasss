"""Train/check the student's local model with predictable output names."""
import argparse,json
from pathlib import Path
from arena.train_example import train
from arena.runner import load_session

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    root=Path(__file__).resolve().parent.parent;out=root/'output';out.mkdir(exist_ok=True)
    model=out/'my_model.onnx'
    if not args.check:
        cfg=json.loads((root/'arena/training_config.json').read_text(encoding='utf-8'))
        if any(type(cfg.get(k)) is not int for k in ('samples','epochs','seed')):raise ValueError('参数须为整数')
        if not 16<=cfg['samples']<=100000 or not 1<=cfg['epochs']<=1000:raise ValueError('samples:16—100000；epochs:1—1000')
        train(root/'teacher-baseline.onnx',model,**cfg)
    predict=load_session(model);predict([0]*225)
    print('检查通过。仅上传 output/my_model.onnx；不要上传整个案例文件夹。')
if __name__=='__main__':main()
