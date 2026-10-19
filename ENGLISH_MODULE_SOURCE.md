# 英语模块来源

英语后续开发主仓库：https://github.com/zephyreal/English （私有）。

2026-10-19：语音安装脚本与下载故障说明从英语仓库经过集成检查的提交
`89c4ecbbff185688a173da5f665971913cd25350` 同步：

- `enable-english-voice.sh`
- `VOICE-INSTALL.md`

其他英语模块源码沿用课程平台v1.4导入的同版快照。英语功能先在英语仓库开发，发布时
固定提交同步到本仓库；课程统一登录、数据库宿主接口与服务器部署仍由本仓库维护。
修改GitHub不会自动更新ECS服务器，仍需拉取代码、执行相应升级或语音安装脚本。

2026-10-19：识别为空诊断、录音回听及相关测试从英语仓库提交
`1c512d17d388c2b6bc589381faa9220f6be68f50` 同步：`english_speech.py`、
`static/english.js`、`test_english_frontend.cjs`、`test_english_speech.py`、
`VOICE-INSTALL.md` 和 `vendor/speaklab/SOURCE.md`。

2026-10-19：千问原生实时语音从英语仓库经过集成检查的提交
`7c37fa7dd704b610f6795620a70a7653250b235a` 同步：
`english_course.py`、`static/english.js`、`static/english.css`、
`test_english_frontend.cjs`、`test_english_realtime.py`。
API接入说明发布为 `ENGLISH_REALTIME.md`。课程平台补充实时语音设置导航和样式引用，
保留统一账号、论文接口及原部署方式；旧本地识别脚本不再需要。

2026-10-19：实时语音错误诊断与取消竞态修正同步自英语仓库提交
`0b0528aa7b0131a1529090d0435d1510f2483e4c`。教师可查看脱敏错误详情；教师调试每日最多60次，学生限额保持6次。

2026-10-19：首次开场生成请求携带明确任务、空开场错误保留连续通话，
同步自英语仓库提交 `4f3cde31cc27de2b2d5716e1e7c61466cb701dd0`。
