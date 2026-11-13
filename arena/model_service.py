"""One-model sandbox service. No game openings, opponent model, or credentials enter this container."""
import json
import os
import sys
from runner import load_session

if os.getenv('ARENA_SANDBOX')!='1':raise SystemExit('该服务只在隔离容器内启动')
try:
    from pathlib import Path
    from function_agent import FunctionAgent
    function_agent=FunctionAgent('/input/agent.py') if Path('/input/agent.py').exists() else None
    predict=None if function_agent else load_session('/input/model.onnx')
    deity=None
    if os.getenv('ARENA_DEITY')=='1':
        from deity import DeityClient
        deity=DeityClient()
    import hashlib
    from pathlib import Path
    print(json.dumps({'ready':True,'deity_sha':hashlib.sha256(Path('/runner/deity-engine.js').read_bytes()).hexdigest() if deity else ''}),flush=True)
except Exception as exc:
    message=str(exc) if isinstance(exc,ValueError) else '模型无法加载，请检查导出格式和算子兼容性'
    print(json.dumps({'ready':False,'error':message[:160]},ensure_ascii=False),flush=True);raise SystemExit(0)
for line in sys.stdin:
    if len(line)>10000:break
    request={}
    try:
        request=json.loads(line);board=request['board']
        if len(board)!=225 or any(type(v) is not int or v not in (-1,0,1) for v in board):raise ValueError()
        if request.get('op')=='choose':
            if deity is None and function_agent is None:raise ValueError()
            import time
            result={'move':function_agent.move(board)} if function_agent else deity.choose(board,predict,time.monotonic()+10)
            reply={'request_id':request['request_id'],**result}
        else:
            value,policy=predict(board)
            reply={'request_id':request['request_id'],'value':value,'policy':policy}
    except Exception:reply={'request_id':request.get('request_id','') if isinstance(request,dict) else '', 'error':'模型未返回有效预测'}
    print(json.dumps(reply,allow_nan=False,separators=(',',':')),flush=True)
