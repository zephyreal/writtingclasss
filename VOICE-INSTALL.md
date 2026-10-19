# 语音安装：模型下载网络失败

网页显示“教师需先启用服务器语音识别”，安装日志含 Hugging Face
`Network is unreachable` / `LocalEntryNotFoundError` 时，表示公开模型未下载成功。
安装尚未启用语音，所以录音按钮会禁用；这时还不是电脑麦克风权限错误。

更新主平台部署快照后，在服务器源代码目录执行安装脚本。

## 官方下载源

```bash
cd /root/writtingclasss
git pull --ff-only origin main
bash enable-english-voice.sh
```

## 选用第三方下载镜像

HF-Mirror（https://hf-mirror.com）是第三方公益镜像，不是 Hugging Face 官方站。
可仅为本次安装显式选择它；不是永久修改服务端点：

```bash
cd /root/writtingclasss
HF_ENDPOINT=https://hf-mirror.com bash enable-english-voice.sh
```

仅下载公开模型，不需要账号或API密钥。脚本不发送隐式认证token，不上传学生录音、
作业或其他课程数据。模型仍在本地执行。镜像在服务器上的连通性需要实际验收；
不能保证境内所有网络都可用，也不能仅凭加载成功证明镜像内容与官方逐字节一致。

## 离线导入

在能访问官方站的电脑上下载完整 `Systran/faster-whisper-tiny.en` 模型目录，包含
真实模型文件（不是Git LFS指针），上传到服务器。例如放在 `/root/tiny.en` 后：

```bash
VOICE_MODEL_DIR=/root/tiny.en bash enable-english-voice.sh
```

这条路径只跳过模型下载，Python依赖仍需安装。不要直接将普通Whisper的 `.pt`
文件当作CTranslate2模型。目录需包含模型权重、配置和tokenizer等完整文件。

## 验证与安全启用

安装先进入临时目录，以网站服务账号运行，完成本地CPU int8模型加载和VAD静音
识别检查后再替换模型并写入READY。失败不会手动伪造启用状态，也不替换已有可用
模型。旧目录会以 `tiny.en.before-*` 留在服务器，确认新版本正常后可由管理员清理。
模型、缓存和运行标记不提交GitHub。

成功后自动重启writing-class。通过HTTPS登录、Ctrl+F5刷新，再点“录一句”，允许
浏览器访问麦克风；如果权限已被拒绝，在浏览器该站点权限中改为允许。

模型验证只证明安装可加载，实际口音识别效果、延迟和麦克风兼容性仍需真实录音测试。
