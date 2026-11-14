"""Load only in an isolated evaluator or a trusted local exercise."""
import importlib.util

class FunctionAgent:
    direct = True
    def __init__(self, path):
        spec = importlib.util.spec_from_file_location('student_agent', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.function = module.choose_move
        if not callable(self.function):
            raise ValueError('缺少choose_move函数')

    def move(self, board):
        grid = [list(board[r*15:(r+1)*15]) for r in range(15)]
        try:
            result = self.function(grid)
        except Exception as exc:
            raise ValueError('choose_move执行出错：'+type(exc).__name__+'；检查索引、变量名和返回值') from exc
        if not isinstance(result, (tuple, list)) or len(result) != 2:
            raise ValueError('请返回(row, col)')
        row, col = result
        if type(row) is not int or type(col) is not int or not (0 <= row < 15 and 0 <= col < 15):
            raise ValueError('行列必须是0至14的整数')
        move = row*15 + col
        if board[move] != 0:
            raise ValueError('落子位置已有棋子')
        return move

    def choose(self, board, deadline):
        return self.move(board)
