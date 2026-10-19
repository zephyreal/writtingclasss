#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo '请在root终端执行'; exit 1; fi
cd "$(dirname "$0")"
if [ ! -f /opt/writing-class/english_speech.py ]; then echo '请先运行 bash upgrade.sh 升级到v1.4'; exit 1; fi
echo '安装可选语音识别，并下载 tiny.en 模型；需要能访问 Python 包源及 Hugging Face。'
echo '采用 CPU int8、单并发；2GB服务器先限小班测试，实际延迟取决于录音长度。'
/opt/writing-class/.venv/bin/pip install -r requirements-voice.txt
install -d -o writingclass -g writingclass -m 700 /var/lib/writing-class/english-asr
runuser -u writingclass -- /opt/writing-class/.venv/bin/python - <<'PY'
from pathlib import Path
from faster_whisper import WhisperModel
from faster_whisper.utils import download_model
root=Path('/var/lib/writing-class/english-asr')
ready=root/'READY'
ready.unlink(missing_ok=True)
download_model('tiny.en',output_dir=str(root/'tiny.en'))
# Validate the installed model and VAD with silence before marking ready.
import numpy as np
m=WhisperModel(str(root/'tiny.en'),device='cpu',compute_type='int8',cpu_threads=1,num_workers=1,local_files_only=True)
segments,_=m.transcribe(np.zeros(16000,dtype=np.float32),language='en',word_timestamps=True,vad_filter=True)
list(segments)
ready.write_text('faster-whisper 1.2.1 / tiny.en / CPU int8 / single concurrency\n')
print('语音模型已安装并完成加载检查')
PY
systemctl restart writing-class
echo '语音识别已启用。公网HTTP页面先上传音频，HTTPS页面可直接调用麦克风。'
