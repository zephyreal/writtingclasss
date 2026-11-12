# 五子棋模型赛：学生入门

本期是模型赛：提交单文件ONNX，平台对双方使用相同的固定搜索。代码ZIP仅用于教师审阅，不会被执行。网页“化神”档含另一套VCT策略，与正式模型赛不是同一引擎。

## 本人电脑上的准备

建议Python 3.12，在解压后的目录执行：

```bash
python -m venv .venv
```

Windows激活：`.venv\Scripts\activate`；Linux/macOS激活：`source .venv/bin/activate`。随后：

```bash
python -m pip install -r arena/requirements.txt
python -m arena.example_model --output my-gomoku.onnx
python -m arena.local_check --model my-gomoku.onnx
```

这是一个输出固定策略的最小接口示例，可用于检查上传流程，不代表强棋力。

## 尝试训练并导出

模板包含教师模型、一个无需GPU的NumPy模仿学习示例。示例从合法随机局面采样，以教师模型的策略和值作为标签，训练小型线性模型并导出ONNX：

```bash
python -m arena.train_example --teacher teacher-baseline.onnx --samples 256 --epochs 5 --output my-trained.onnx
python -m arena.local_check --model my-trained.onnx
```

该示例的目标是跑通“采样—训练—导出—检查”，不保证能战胜教师。应如实说明使用了教师标签；后续可改进数据、网络和训练方法。

## 统一接口

- 输入名称`board`，float32，静态形状`[1,3,15,15]`。
- 三个通道按顺序是：当前行动方的棋子、对方棋子、空位；对应位置为1，其余为0。
- 输出名称`value`和`policy`。`value`为[-1,1]内的当前行动方局面价值；`policy`包含按行展开的225个有限非负概率/权重（建议Softmax）（位置=行×15+列）。平台会屏蔽已有棋子位置并归一化。
- 输出单文件、确定性的推理ONNX，不带外部权重、不使用随机/循环/自定义算子，不提交`.pt`、`.pth`或pickle。
- 模型最大20MB，代码存档ZIP最大5MB。此限制与论文写作模块的3MB文档上限分别管理。

本地检查只检查本人可信模型，不能产生正式成绩。正式结果由独立、隔离的评测机生成。不要在自己电脑上随意运行其他人来源不明的模型或代码。

## 提交与查看

进入“智能制造课程设计 → 模型竞赛”，选比赛，上传模型并说明本版改进。可以附代码ZIP，但不要包含密钥、环境密码或无关个人资料。

练习赛取每人最新已完成版本，同分并列；排队/失败不会覆盖之前的有效成绩。完整评测通过后才能排名。结课赛截止前取最后一个未撤回版本，截止后统一评测，教师发布前不展示成绩和棋谱。

棋谱默认仅本人和教师可见，可主动允许班内查看，也可停止公开；同学不能下载你的模型或代码。运行中及已有成绩的版本不能自行删除。失败、超时和规则不合格有对应提示，基础设施异常由教师重试。
