"""Offline bridge for the trusted frozen browser Deity engine; production runs inside runsc only."""
import json
import os
import select
import subprocess
import time
from pathlib import Path

class DeityClient:
    def __init__(self,engine=None):
        root=Path(__file__).resolve().parent
        engine=engine or root/'deity-engine.js'
        self.buffer=bytearray()
        self.process=subprocess.Popen(['node','--max-old-space-size=128',str(root/'deity_bridge.cjs'),str(engine)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        try:
            if self.read(time.monotonic()+10).get('ready') is not True:raise ValueError('化神引擎未就绪')
        except Exception:self.close();raise
    def send(self,data):
        data=memoryview(json.dumps(data,allow_nan=False,separators=(',',':')).encode()+b'\n')
        while data:data=data[os.write(self.process.stdin.fileno(),data):]
    def read(self,deadline):
        while len(self.buffer)<=262144:
            end=self.buffer.find(b'\n')
            if end>=0:
                line=self.buffer[:end];del self.buffer[:end+1];return json.loads(line)
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([self.process.stdout],[],[],remaining)[0]:raise TimeoutError('化神搜索超时')
            chunk=os.read(self.process.stdout.fileno(),8192)
            if not chunk:raise ValueError('化神引擎中断')
            self.buffer.extend(chunk)
        raise ValueError('化神输出超过协议上限')
    def choose(self,board,predict,deadline):
        self.send({'board':board})
        for _ in range(152):
            message=self.read(deadline)
            if message.get('type')=='move':
                move=message.get('move')
                if type(move) is not int or not 0<=move<225 or board[move]:raise ValueError('化神落子无效')
                return message
            if message.get('type')!='predict':raise ValueError('化神协议无效')
            relative=message.get('board')
            if not isinstance(relative,list) or len(relative)!=225 or any(type(v) is not int or v not in (-1,0,1) for v in relative):raise ValueError('化神推理棋盘无效')
            value,policy=predict(relative);self.send({'value':value,'policy':list(policy)})
        raise ValueError('化神搜索超过150次推理上限')
    def close(self):
        if self.process.poll() is None:self.process.kill()
        self.process.wait(timeout=5)
        self.process.stdin.close();self.process.stdout.close()
