"""仅运行自己编写或教师提供的可信代码；本地成绩不上传。"""
import json
import time
import webbrowser
from pathlib import Path
from function_agent import FunctionAgent
from arena_engine import five


def main():
    root=Path(__file__).resolve().parent
    agent=FunctionAgent(root/'agent.py')
    config=json.loads((root/'competition.json').read_text())['config']
    board=[0]*225;records=[];winner=0;error=''
    try:
        # 练习对手为确定性的邻近落子策略，不是正式教师基线。
        for turn in range(225):
            color=1 if turn%2==0 else -1
            start=time.monotonic()
            if color==1:
                move=agent.move(board)
            else:
                empty=[i for i,v in enumerate(board) if not v]
                def score(i):
                    r,c=divmod(i,15)
                    neighbors=sum(bool(board[y*15+x]) for y in range(max(0,r-1),min(15,r+2)) for x in range(max(0,c-1),min(15,c+2)))
                    return neighbors*10-abs(r-7)-abs(c-7)
                move=max(empty,key=score)
            elapsed=(time.monotonic()-start)*1000
            if color==1 and elapsed>config['move_ms']:
                raise ValueError('超过本场每步时限')
            board[move]=color;records.append([move,color,round(elapsed,2)])
            if five(board,move,color):winner=color;break
    except Exception as exc:
        error=str(exc)
    import html
    stones=''.join(f'<circle cx="{(i%15)*30+20}" cy="{(i//15)*30+20}" r="12" fill="'+('black' if v==1 else 'white')+'" stroke="black"/>' for i,v in enumerate(board) if v)
    lines=''.join(f'<path d="M20 {20+i*30}H440 M{20+i*30} 20V440" stroke="#aaa"/>' for i in range(15))
    rows=''.join(f'<tr><td>{n+1}</td><td>{"自己" if color==1 else "练习对手"}</td><td>{move//15}, {move%15}</td><td>{ms}</td></tr>' for n,(move,color,ms) in enumerate(records))
    title=error or ('自己获胜' if winner==1 else '练习对手获胜' if winner==-1 else '平局')
    output=root/'output';output.mkdir(exist_ok=True)
    report=output/'report.html'
    report.write_text(f'<meta charset="utf-8"><title>本地练习</title><h1>{html.escape(title)}</h1><p>仅为入门检查，对手不是正式教师基线，不代表正式胜率。只上传agent.py。</p><svg width="460" height="460">{lines}{stones}</svg><table><tr><th>步</th><th>执子方</th><th>行,列（从0开始）</th><th>毫秒</th></tr>{rows}</table>',encoding='utf-8')
    print(title,'\n报告：',report)
    webbrowser.open(report.as_uri())

if __name__=='__main__':main()
