"""Dedicated-machine gVisor acceptance test: trusted teacher model versus itself, no website token."""
import argparse
import hashlib
import shutil
from pathlib import Path
from arena.worker import Worker,runtime_info
from arena_engine import ENGINE,DEITY_ENGINE,openings,verify_games

class SmokeWorker(Worker):
    def request(self,*args,**kwargs):return {'ok':True}
    def download(self,job,kind,destination):shutil.copyfile(self.baseline,destination)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--image',default='writing-course-arena:v1');parser.add_argument('--deity',action='store_true');args=parser.parse_args()
    image,fingerprint=runtime_info(args.image)
    worker=SmokeWorker('https://localhost','smoke-no-credentials','smoke',args.image)
    worker.baseline=Path(__file__).parents[1]/'course_assets/gomoku/gomoku_uint8_qop_u8u8.onnx'
    digest=hashlib.sha256(worker.baseline.read_bytes()).hexdigest();bank=openings('trusted-sandbox-smoke-v1',1)
    job={'id':0,'lease':'smoke','config':{'engine':ENGINE,'pairs':1,'simulations':2,'move_ms':3000,'job_seconds':240,'memory_mb':1024},'openings':bank,'model_hash':digest,'baseline_hash':digest}
    if args.deity:
        job['config'].update(engine=DEITY_ENGINE,simulations=150,move_ms=5000,job_seconds=900,deity_sha=hashlib.sha256((Path(__file__).parents[1]/'course_assets/gomoku/ai-worker.js').read_bytes()).hexdigest())
    result=worker.execute(job,image)
    if not result or result['status']!='completed':raise SystemExit('隔离验收未通过：'+str(result))
    report=verify_games(bank,result['games'],job['config']['move_ms'])
    if not args.deity and report['score']!=50:raise SystemExit('镜像对弈结果不一致，暂不接入正式比赛')
    print('化神隔离挑战赛、完整棋谱验收通过；学生比赛分：'+str(report['score']) if args.deity else 'gVisor双模型隔离、可信裁判、完整棋谱验收通过；基准互测为50分。')
    print('运行环境指纹：'+fingerprint)
