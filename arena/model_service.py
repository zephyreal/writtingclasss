"""One-model sandbox service. No game openings, opponent model, or credentials enter this container."""
import json
import os
import sys
from runner import load_session

if os.getenv('ARENA_SANDBOX')!='1':raise SystemExit('该服务只在隔离容器内启动')
try:
    predict=load_session('/input/model.onnx')
    print(json.dumps({'ready':True}),flush=True)
except Exception as exc:
    message=str(exc) if isinstance(exc,ValueError) else '模型无法加载，请检查导出格式和算子兼容性'
    print(json.dumps({'ready':False,'error':message[:160]},ensure_ascii=False),flush=True);raise SystemExit(0)
for line in sys.stdin:
    if len(line)>10000:break
    request={}
    try:
        request=json.loads(line);board=request['board']
        if len(board)!=225 or any(type(v) is not int or v not in (-1,0,1) for v in board):raise ValueError()
        value,policy=predict(board)
        reply={'request_id':request['request_id'],'value':value,'policy':policy}
    except Exception:reply={'request_id':request.get('request_id','') if isinstance(request,dict) else '', 'error':'模型未返回有效预测'}
    print(json.dumps(reply,allow_nan=False,separators=(',',':')),flush=True)
