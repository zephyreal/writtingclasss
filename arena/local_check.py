"""Check your own exported model locally. Never used by the website or production worker."""
import argparse
from pathlib import Path
from arena.runner import ModelClient

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='只检查本人可信模型；不代替正式隔离评测')
    parser.add_argument('--model',required=True);args=parser.parse_args();client=None
    try:
        client=ModelClient(Path(args.model));value,policy=client.predict([0]*225,__import__('time').monotonic()+5)
        print('输入输出检查通过；value=',round(value,5),'；policy长度=',len(policy),'；概率和=',round(sum(policy),6))
        print('此结果不进入网站排行榜，正式成绩由隔离评测机生成。')
    finally:
        if client:client.close()
