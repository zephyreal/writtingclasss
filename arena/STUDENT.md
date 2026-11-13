# 从本地训练到上传：第一次使用

网站只需“下载案例包、上传模型、等待结果”。本地练习不限次数。

1. 安装Python 3.12（64位），勾选 Add Python to PATH。将案例ZIP全部解压，不在压缩包里运行。
2. 双击01_setup.bat，首次联网安装依赖。失败时先解决错误，不要继续。
3. 双击02_train.bat，默认用CPU训练一个小模型。出现“检查通过”后，在output文件夹得到 **my_model.onnx**。
4. 回到网站上传 **output/my_model.onnx**，填写一句本次修改说明。不要上传.py、.pth或整个文件夹。
5. 上传成功可关闭网页。之后在“我的版本”查看成绩、棋谱和报告。结课赛由教师统一发布。
6. 用文本编辑器修改arena/training_config.json中的samples（样本数）、epochs（训练轮数），一次只改一项，重新训练后提交比较。

也可在终端运行：python -m arena.student_workflow；只检查已有模型：python -m arena.student_workflow --check。
Linux/macOS：python3 -m venv .venv；.venv/bin/python -m pip install -r arena/requirements.txt；.venv/bin/python -m arena.student_workflow。

## 三个小实验
A：原样运行一次，理解输入棋盘、输出落子建议和局面价值。
B：保持epochs不变，将samples从256改为512，比较执黑/执白胜负。数据更多不保证棋力提高。
C：比较不同训练设置，记录“我改了什么—预期怎样—实际怎样”；进一步修改train_example.py的数据或网络。
这是模仿学习入门案例，使用教师标签，需要如实说明。示例提交用于熟悉流程，不能代替自己的课程设计。

## 遇到问题
- 找不到Python：安装Python 3.12并添加PATH；不是直接双击.py文件。
- 缺少onnx/numpy：重新运行01_setup.bat，检查依赖下载是否成功。
- 找不到my_model.onnx：02_train.bat没有完成，先看窗口错误。
- 训练慢：先用默认256个样本、5轮，不要立即增加到很大。
- 文件不合格：双击03_check.bat检查自己生成的模型；正式运行仍由服务器隔离检查。
- 评测机离线：文件已保存，无需反复上传，等待教师处理。

以下为进阶接口及规则，初次使用可稍后阅读。

# 五子棋模型赛：学生入门

本期是模型赛：提交单文件ONNX，教师可选化神挑战赛或统一MCTS练习赛；以页面冻结规则为准。代码ZIP仅用于教师审阅，不会被执行。化神挑战赛复用网页化神搜索代码（一步必赢/必堵、严格VCF、自适应50/100/150次MCTS），学生模型统一150次MCTS；双方每步相同时限。统一MCTS练习赛则双方使用相同固定搜索。

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

提交区显示今天还可提交几次（北京时间每日重置）；撤回不返还次数。首次可用最小示例检查流程，再提交训练版本。

练习赛取每人最新已完成版本，同分并列；排队/失败不会覆盖之前的有效成绩。完整评测通过后才能排名。结课赛截止前取最后一个未撤回版本，截止后统一评测，教师发布前不展示成绩和棋谱。

棋谱默认仅本人和教师可见，可主动允许班内查看，也可停止公开；同学不能下载你的模型或代码。运行中及已有成绩的版本不能自行删除。失败、超时和规则不合格有对应提示，基础设施异常由教师重试。

完整评测后，可下载本版HTML报告（打开后可打印为PDF）和含完整棋谱的JSON报告。报告包含执黑/执白成绩、异常判负局数、模型校验值和固定赛制，便于整理实验对比。报告只向本人及教师开放；结课赛须等教师发布。

教师基准下载的是神经网络权重，不包含完整化神搜索。模仿学习示例学习的是网络输出，不等于复制化神全部棋力。离线CPU与浏览器WASM的数值及耗时可能不同，比赛以固定评测端结果为准。
