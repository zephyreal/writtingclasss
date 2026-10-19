"""Small CPU adapter following SpeakLab's word-timestamp ASR contract.

No audio is persisted. Optional dependencies are imported only when enabled.
Fluency arithmetic lives in the vendored MIT SpeakLab module, never in the LLM.
"""
import io
import os
import threading
from pathlib import Path
from fastapi import HTTPException
from vendor.speaklab.fluency import analyse

SLOT = threading.Lock()
MODEL = None
MAX_SECONDS = 60


def enabled(data):
    return (Path(data) / 'english-asr' / 'READY').is_file()


def transcribe(raw, data):
    if not enabled(data):
        raise HTTPException(503, '语音识别尚未安装，请教师按英语模块说明启用；可以先用文字练习')
    if not SLOT.acquire(blocking=False):
        raise HTTPException(429, '语音识别正在处理另一段录音，请稍后重试')
    try:
        return _transcribe(raw, data)
    finally:
        SLOT.release()


def _transcribe(raw, data):
    global MODEL
    try:
        import av
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError:
        raise HTTPException(503, '语音组件未完整安装，请教师重新执行 enable-english-voice.sh')
    # Adapted from SpeakLab infra/asr/app.py: PyAV mono resampling and decoded
    # sample duration. Stop DURING decoding, rather than trusting container metadata.
    chunks, samples = [], 0
    try:
        with av.open(io.BytesIO(raw)) as container:
            if not container.streams.audio:
                raise ValueError('no audio')
            resampler = av.audio.resampler.AudioResampler(format='s16', layout='mono', rate=16000)
            for frame in container.decode(container.streams.audio[0]):
                for resampled in resampler.resample(frame):
                    part = resampled.to_ndarray().reshape(-1)
                    samples += len(part)
                    if samples > MAX_SECONDS * 16000:
                        raise HTTPException(413, '每段录音最多60秒，请分段练习')
                    chunks.append(part)
            for resampled in resampler.resample(None):
                part = resampled.to_ndarray().reshape(-1)
                samples += len(part)
                if samples > MAX_SECONDS * 16000:
                    raise HTTPException(413, '每段录音最多60秒')
                chunks.append(part)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, '无法解码音频，请上传有效的 WAV、WebM、MP3、M4A 或 OGG')
    if samples < 3200:
        raise HTTPException(400, '录音过短，请说一句完整的英语')
    audio = np.concatenate(chunks).astype(np.float32) / 32768.0
    model_path = Path(data) / 'english-asr' / 'tiny.en'
    try:
        if MODEL is None:
            MODEL = WhisperModel(str(model_path), device='cpu', compute_type='int8', cpu_threads=1, num_workers=1, local_files_only=True)
        segments, _ = MODEL.transcribe(audio, language='en', beam_size=1,
            word_timestamps=True, vad_filter=True, condition_on_previous_text=False)
        words, texts, fixups = [], [], 0
        duration_ms = round(samples / 16)
        for segment in segments:
            texts.append(segment.text)
            for word in segment.words or []:
                original = (round(word.start * 1000), round(word.end * 1000))
                start = min(duration_ms, max(0, original[0]))
                end = min(duration_ms, max(start, original[1]))
                fixups += (start, end) != original
                words.append({'w': word.word.strip(), 'start_ms': start, 'end_ms': end})
    except Exception:
        raise HTTPException(503, '本地语音识别失败，请稍后重试或联系教师检查模型安装')
    text = ''.join(texts).strip()
    if not text or not words:
        raise HTTPException(400, '没有识别到英语语音，请靠近麦克风再试一次')
    if len(text) > 2000:
        raise HTTPException(400, '识别文本过长，请缩短录音')
    metrics = analyse(words).as_columns()
    # This is silence after pressing record, NOT conversational response latency.
    metrics['leading_silence_ms'] = metrics.pop('response_latency_ms')
    return {'text': text, 'metrics': metrics, 'words': words, 'duration_ms': duration_ms,
            'timestamp_fixups': fixups, 'model': 'faster-whisper/tiny.en:int8', 'pause_threshold_ms': 300}
