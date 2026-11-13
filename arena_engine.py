"""Versioned Gomoku rules and deterministic shared search; no model loading on the web server."""
import math
import random
import time

ENGINE='gomoku-model-v1'
DEITY_ENGINE='gomoku-deity-v1'
ENGINES=(ENGINE,DEITY_ENGINE)
SIZE=15
CELLS=225
DIRECTIONS=((0,1),(1,0),(1,1),(1,-1))


def five(board,move,color):
    r,c=divmod(move,SIZE)
    for dr,dc in DIRECTIONS:
        n=1
        for sign in (-1,1):
            rr,cc=r+sign*dr,c+sign*dc
            while 0<=rr<SIZE and 0<=cc<SIZE and board[rr*SIZE+cc]==color:
                n+=1;rr+=sign*dr;cc+=sign*dc
        if n>=5:return True
    return False


def position(moves):
    board=[0]*CELLS;winner=0
    for i,move in enumerate(moves):
        if type(move) is not int or not 0<=move<CELLS or board[move] or winner:raise ValueError('棋谱有越界、重复落子或终局后继续落子')
        color=1 if i%2==0 else -1;board[move]=color
        if five(board,move,color):winner=color
    return board,winner


def winning_move(board,color):
    for i,x in enumerate(board):
        if x:continue
        board[i]=color;win=five(board,i,color);board[i]=0
        if win:return i
    return None


def openings(seed,pairs):
    rng=random.Random(seed);bank=[];seen=set();pool=[r*15+c for r in range(5,10) for c in range(5,10)]
    while len(bank)<pairs:
        seq=[112]+rng.sample([x for x in pool if x!=112],rng.choice((3,5,7)))
        if tuple(seq) in seen:continue
        b,w=position(seq)
        if w or winning_move(b,1) is not None or winning_move(b,-1) is not None:continue
        bank.append(seq);seen.add(tuple(seq))
    return bank


def verify_games(bank,games,move_ms):
    if len(games)!=len(bank)*2:raise ValueError('有效报告必须包含全部黑白交换对局')
    wins=draws=losses=0;student_times=[];normalized=[]
    for index,g in enumerate(games):
        opening=bank[index//2];color=1 if index%2==0 else -1
        moves=g['moves'];times=g.get('times_ms',[]);fault=g.get('fault','')
        if g['index']!=index or g['student_color']!=color or moves[:len(opening)]!=opening:raise ValueError('对局编号、颜色或开局与固定赛制不符')
        if len(moves)>CELLS or len(times)!=len(moves)-len(opening):raise ValueError('棋谱或计时长度不完整')
        b,winner=position(moves)
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 or v>move_ms+100 for v in times):raise ValueError('计时超出有效范围')
        if fault:
            turn=1 if len(moves)%2==0 else -1
            if winner or len(moves)==CELLS or turn!=color or fault not in ('student_timeout','student_error','student_illegal'):raise ValueError('弃权原因与棋谱不符')
            winner=-color
        elif not winner and len(moves)!=CELLS:raise ValueError('未结束的棋谱不能计为平局')
        for i,t in enumerate(times,len(opening)):
            if (1 if i%2==0 else -1)==color:student_times.append(t)
        if winner==color:wins+=1
        elif winner==-color:losses+=1
        else:draws+=1
        normalized.append({'index':index,'student_color':color,'moves':moves,'times_ms':times,'winner':winner,'fault':fault,'opening_length':len(opening)})
    count=len(games)
    return {'wins':wins,'draws':draws,'losses':losses,'games':count,'score':round(100*(wins+draws*.5)/count,4),
        'mean_move_ms':round(sum(student_times)/len(student_times),2) if student_times else None,'replays':normalized}


class Node:
    def __init__(self,move=-1,prior=1):
        self.move=move;self.prior=prior;self.n=0;self.w=0.;self.q=0.;self.children=None;self.terminal=None


def choose(board,color,predict,simulations,deadline):
    """Same policy/value perspective and PUCT sign convention as the existing browser MCTS.
    Fixed work, ascending-index ties, immediate win/block. VCT is intentionally not part of v1.
    """
    if time.monotonic()>deadline:raise TimeoutError()
    for stone in (color,-color):
        forced=winning_move(board,stone)
        if forced is not None:return forced
    root=Node()
    for _ in range(simulations):
        if time.monotonic()>deadline:raise TimeoutError()
        b=board[:];node=root;path=[node];turn=color
        while node.children:
            node=max(node.children,key=lambda ch:.8*ch.prior*math.sqrt(path[-1].n+1)/(1+ch.n)-ch.q)
            b[node.move]=turn;path.append(node)
            if node.terminal is not None:break
            if five(b,node.move,turn):node.terminal=-1.;break
            if all(b):node.terminal=0.;break
            turn=-turn
        if node.terminal is not None:value=node.terminal
        else:
            relative=[v*turn for v in b];value,policy=predict(relative,deadline)
            node.children=[Node(i,policy[i]) for i,v in enumerate(b) if not v]
        for n in reversed(path):
            n.n+=1;n.w+=value;n.q=n.w/n.n;value=-value
    if time.monotonic()>deadline:raise TimeoutError()
    if not root.children:raise ValueError('没有可落子位置')
    return max(root.children,key=lambda n:(n.n,n.prior,-n.move)).move


def play_game(opening,student_color,student,baseline,cfg,index):
    moves=opening[:];board,winner=position(moves);times=[];fault=''
    while not winner and len(moves)<225:
        color=1 if len(moves)%2==0 else -1;agent=student if color==student_color else baseline
        start=time.monotonic();deadline=start+cfg['move_ms']/1000
        try:
            if (color==student_color and cfg.get('submission')=='function-v1') or (color!=student_color and cfg.get('engine')==DEITY_ENGINE):
                move=agent.choose([v*color for v in board],deadline)
            else:move=choose(board,color,agent.predict,cfg['simulations'],deadline)
            elapsed=(time.monotonic()-start)*1000
            if elapsed>cfg['move_ms']:raise TimeoutError()
            if type(move) is not int or not 0<=move<225 or board[move]:raise ArithmeticError()
        except (TimeoutError,ValueError,ArithmeticError) as exc:
            if color!=student_color:raise RuntimeError('教师基准运行异常，本次不产生比赛分数')
            fault='student_timeout' if isinstance(exc,TimeoutError) else 'student_illegal' if isinstance(exc,ArithmeticError) else 'student_error';break
        board[move]=color;moves.append(move);times.append(round(elapsed,3))
        if five(board,move,color):winner=color
    return {'index':index,'student_color':student_color,'moves':moves,'times_ms':times,'fault':fault}

