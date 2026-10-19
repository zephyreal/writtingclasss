> 英语模块已升级为千问连续语音。升级及填写API说明见 [ENGLISH_REALTIME.md](ENGLISH_REALTIME.md)，无须安装本地语音模型。

# 智学工坊 · 四课程教学平台 v1.3

课程门户包含：学术论文写作、机械工程专业英语、智能装备基础、智能制造课程设计。论文写作保留已有完整功能；专业英语和智能装备基础暂为待建设页面；智能制造课程设计接入AI五子棋案例。学生统一注册登录。

- **已有网站升级**：按 `UPGRADE-v1.3.md` 执行 `bash upgrade.sh`。保留现有账号、作业、课件和成绩。
- **第一次安装**：Ubuntu root终端运行 `bash install.sh`，安装时自行设置教师密码，默认账号teacher。
- **GitHub托管**：参阅 `GITHUB.md`。代码与学生数据分开，仓库建议设为私有。
- **AI接口**：https://api.deepseek.com，模型deepseek-flash，密钥仅在服务器后台配置。真实API待配置后联调。
- **先测试**：当前HTTP站点先使用测试账号和测试稿；正式教学前配置HTTPS。

## 运行位置

程序：`/opt/writing-class`；数据和密钥：`/var/lib/writing-class`；服务：`writing-class`；反向代理：Nginx。应用监听127.0.0.1:8000，不需对公网开放该端口。运行时使用独立的writingclass系统用户，单worker串行处理AI预审。

## 日常检查

```bash
systemctl status writing-class --no-pager
journalctl -u writing-class -n 60 --no-pager
curl http://127.0.0.1:8000/healthz
```

上传PPT/PPTX供学生下载，另传对应PDF可在线阅读。教师课件上限50MiB，学生论文不超过5MB。学生提交Word请用docx，不支持旧doc。自动预审20页以内；超过或解析失败由教师处理。两核2GB建议先小规模试用，正式并发能力待压测。

练习使用统一24题，每题首次作答计分，未答计0，巩固和AI拓展不改首次成绩。掌握度用于推荐而非最终评分。教师可以发布作业、下载原文、查看AI报告、退回、恢复人工复核、发布成绩与导出CSV。

## 本地验证

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q test_app.py
node --check static/app.js
node test_frontend.cjs
bash -n install.sh
bash -n upgrade.sh
```

本地PDF/Word渲染测试需要LibreOffice；未安装时Word真实转换测试跳过。旧版本迁移测试需要上一级目录的writing-class-v1.zip。本次交付已执行包含真实Word/PDF转换和旧版迁移的完整21项测试。无真实API凭证时测试用模拟响应，不产生模型费用。

## 备份与数据保护

升级脚本会短暂停站，将旧代码和完整数据目录备份到/root/course-backups。日常还应将数据库、上传文件与AI配置定期备份到受控的服务器外位置。备份含学生论文和API密钥，限制访问。不要把数据目录或备份上传到GitHub或作为静态网站目录公开。

正式配置HTTPS后，在/etc/systemd/system/writing-class.service设置Environment=COOKIE_SECURE=true，执行systemctl daemon-reload和systemctl restart writing-class。不要在仅HTTP时启用secure cookie。

## 当前边界

本版单课程、固定示例题库；无在线题库编辑、班级分组、邮件找回、在线支付或经过标注验证的自动评分模型。形式预审是助教工具，争议可由教师纠正。AI不核验实验数据、参考文献真实性和研究创新性。后台队列在进程内，重启中断任务后可重新触发。

## 智能制造课程设计

页面内或新窗口打开AI五子棋案例。原始代码与ONNX模型从本服务器加载，推理运行库沿用源项目的jsDelivr依赖。详见course_assets/GOMOKU_SOURCE.md。当前对弈不自动计入课程成绩。


## v1.4 英语对话

机械工程专业英语已开放话题问答、慢速朗读、提示、历史记录与学习画像；可选本地语音识别。
升级、启用语音、HTTPS和新闻源说明见 [UPGRADE-v1.4.md](UPGRADE-v1.4.md)。
复用 MIT SpeakLab 的时序统计及情景素材，未接入发音评分。


## 学生删除未批改作业

课程作业页对本人未批改的提交显示“删除未批改作业”。删除后可在截止时间前重新提交，
截止后不会因删除而开放重交。AI排队/批改中、已有AI结果、教师评分或评语、退回/复核
状态、已有历史评阅版本均不能自行删除；需要教师退回修改。AI失败或中断且没有任何
评阅结果的首次提交可以删除。后端在同一数据库写事务内校验状态、归属并记录删除操作，
移除提交及原上传文件；其他学生和教师不能通过此学生接口删除。新提交不复用已删除ID。

服务器更新方式：`git pull --ff-only origin main`，然后 `bash upgrade.sh`，刷新网页。


## v1.5 作业编辑与批改队列

教师可编辑作业及评分量表，AI按本次要求给建议分；支持一键未评作业批改、指定时间、
每日自动安排和避开高峰。说明与升级步骤见 [UPGRADE-v1.5.md](UPGRADE-v1.5.md)。


v1.5.1 修复审核完成却因引文未匹配而丢弃建议分的问题；无分数的旧记录请打开批改，
点击“补评分 / 重新AI批改”。批改页可查看后端评分引擎版本和无分数的具体原因。


语音模型下载出现 `Network is unreachable` 时，使用更新后的安装脚本选择下载端点或
离线导入；具体步骤见 [VOICE-INSTALL.md](VOICE-INSTALL.md)。


语音适配器1.4.1增加麦克风选择、输入音量条、本地录音回听和转写为空的诊断，
调整短句VAD并保留无时间戳的转写文字。运行upgrade.sh后刷新即可，无需重装模型。
