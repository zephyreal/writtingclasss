#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo '请在root终端执行'; exit 1; fi
cd "$(dirname "$0")"
if [ ! -f /opt/writing-class/english_speech.py ]; then echo '请先运行 bash upgrade.sh 安装英语模块'; exit 1; fi
VOICE_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"
export VOICE_ENDPOINT
python3 - <<'PY'
import os
from urllib.parse import urlparse
p=urlparse(os.environ['VOICE_ENDPOINT'])
if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment:
    raise SystemExit('HF_ENDPOINT须为不含账号、密钥或查询参数的HTTPS地址')
PY
/opt/writing-class/.venv/bin/pip install -r requirements-voice.txt
VOICE_ROOT=/var/lib/writing-class/english-asr
install -d -o writingclass -g writingclass -m 700 "$VOICE_ROOT" "$VOICE_ROOT/hub-cache"
exec 9>"$VOICE_ROOT/install.lock"
flock -n 9 || { echo '另一项语音安装正在进行，请等待完成'; exit 1; }
VOICE_STAGE=$(mktemp -d "$VOICE_ROOT/install-XXXXXX")
trap 'rm -rf "$VOICE_STAGE"' EXIT
VOICE_OFFLINE=0
if [ -n "${VOICE_MODEL_DIR:-}" ]; then
    if [ ! -d "$VOICE_MODEL_DIR" ]; then echo 'VOICE_MODEL_DIR目录不存在'; exit 1; fi
    cp -rL "$VOICE_MODEL_DIR/." "$VOICE_STAGE/"
    VOICE_OFFLINE=1
    echo '验证已导入的本地模型，不访问模型下载站。'
else
    echo "下载公开 tiny.en 模型，下载端点：$VOICE_ENDPOINT"
    echo '如默认端点连接失败，可显式设置HF_ENDPOINT，或用VOICE_MODEL_DIR导入完整本地模型。'
fi
chown -R writingclass:writingclass "$VOICE_STAGE"
runuser -u writingclass -- env HF_ENDPOINT="$VOICE_ENDPOINT" HF_HOME="$VOICE_ROOT/hub-cache" \
    HF_TOKEN= HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1 \
    HF_HUB_ETAG_TIMEOUT=15 HF_HUB_DOWNLOAD_TIMEOUT=60 \
    VOICE_STAGE="$VOICE_STAGE" VOICE_OFFLINE="$VOICE_OFFLINE" \
    /opt/writing-class/.venv/bin/python - <<'PY'
import os
from pathlib import Path
from faster_whisper import WhisperModel
from faster_whisper.utils import download_model
root=Path(os.environ['VOICE_STAGE'])
if os.environ['VOICE_OFFLINE']!='1':
    try:download_model('tiny.en',output_dir=str(root))
    except Exception as e:
        raise SystemExit('模型下载失败（'+type(e).__name__+'）。服务器无法访问下载源或文件不完整；尚未启用语音。请换下载端点或离线导入模型，不要手动创建READY。')
try:
    import numpy as np
    model=WhisperModel(str(root),device='cpu',compute_type='int8',cpu_threads=1,num_workers=1,local_files_only=True)
    segments,_=model.transcribe(np.zeros(16000,dtype=np.float32),language='en',word_timestamps=True,vad_filter=True)
    list(segments)
except Exception as e:
    raise SystemExit('模型加载/语音检测验证失败（'+type(e).__name__+'），未替换已安装模型；请提供完整兼容的faster-whisper模型。')
(root/'VERIFIED').write_text('faster-whisper 1.2.1 / tiny.en / CPU int8 / single concurrency\n')
print('模型下载/导入完成，加载与语音检测检查通过。')
PY
if [ -e "$VOICE_ROOT/tiny.en" ]; then
    mv "$VOICE_ROOT/tiny.en" "$VOICE_ROOT/tiny.en.before-$(date +%Y%m%d-%H%M%S)-$$"
fi
mv "$VOICE_STAGE" "$VOICE_ROOT/tiny.en"
install -o writingclass -g writingclass -m 600 "$VOICE_ROOT/tiny.en/VERIFIED" "$VOICE_ROOT/READY"
systemctl restart writing-class
echo '语音识别已启用。请打开HTTPS网站，Ctrl+F5刷新后允许麦克风权限。'
