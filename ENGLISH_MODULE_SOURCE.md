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
