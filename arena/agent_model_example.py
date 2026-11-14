"""只修改并上传 agent.py。无需主程序、模型权重或工程文件。
board是15行×15列的列表：1=自己，-1=对手，0=空位。
无论执黑还是执白，输入始终使用自己的视角。行列均从0开始。
返回(row, col)，例如(7, 7)是中心。只可落在空位。
规则：15×15、无禁手、连续五子及以上获胜。每步时限由比赛给定。
"""

from gomoku_model import evaluate

DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
MODEL_WEIGHT = 1000.0  # 模型偏好权重；一次只改变一个参数
DEFENSE = 1.1  # 防守权重：先只修改此值，比较棋谱与胜率


def line_score(board, row, col, player):
    """假设在空位落子，观察四个方向的连续棋子与开放端。"""
    best = 0
    for dr, dc in DIRECTIONS:
        count, opened = 1, 0
        for sign in (-1, 1):
            r, c = row + sign*dr, col + sign*dc
            while 0 <= r < 15 and 0 <= c < 15 and board[r][c] == player:
                count += 1
                r, c = r + sign*dr, c + sign*dc
            if 0 <= r < 15 and 0 <= c < 15 and board[r][c] == 0:
                opened += 1
        if count >= 5:
            return 1000000
        if opened:
            best += (10 ** count) * opened
    return best


def choose_move(board):
    """核心函数：读棋盘 → 找候选点 → 攻防评分 → 返回一个落子。"""
    empty = [(r, c) for r in range(15) for c in range(15) if board[r][c] == 0]
    if not empty:
        raise ValueError('棋盘已满')
    if len(empty) == 225:
        return 7, 7

    # 第一步：自己能赢就直接赢；第二步：堵住对方的一步成五。
    for player in (1, -1):
        for r, c in empty:
            if line_score(board, r, c, player) >= 1000000:
                return r, c

    # 模型不是完整化神：先保证一步取胜/防守，再用固定模型辅助排序。
    value, policy = evaluate(board)
    # value仅供进一步搜索使用；这里用policy融合规则评分。
    def score(point):
        r, c = point
        attack = line_score(board, r, c, 1)
        defense = line_score(board, r, c, -1)
        center = abs(r-7) + abs(c-7)
        return attack + DEFENSE*defense - center + MODEL_WEIGHT*policy[r][c]
    return max(empty, key=score)
