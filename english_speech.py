"""Small CPU adapter following SpeakLab's word-timestamp ASR contract.

No audio is persisted. Optional dependencies are imported only when enabled.
Fluency arithmetic lives in the vendored MIT SpeakLab module, never in the LLM.
"""
import io
import math
import re
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
    signal=signal_info(audio)
    if signal['rms']<0.00008 and signal['peak']<0.0005:
        raise HTTPException(400,'服务器收到的录音接近静音（'+str(round(samples/16000,1))+'秒）。请先回听录音，检查所选麦克风及系统输入音量；这不表示没有说英语。')
    model_path = Path(data) / 'english-asr' / 'tiny.en'
    warnings=[]
    # Gentle bounded gain for quiet input; statistics still describe original audio.
    gain=min(8.0,0.02/max(signal['rms'],1e-9),0.95/max(signal['peak'],1e-9))
    if gain>1.2:
        audio=np.clip(audio*gain,-1,1)
        warnings.append('输入音量较低，识别前已适度放大；可先回听录音。')
    fallback=False
    try:
        if MODEL is None:
            MODEL = WhisperModel(str(model_path), device='cpu', compute_type='int8', cpu_threads=1, num_workers=1, local_files_only=True)
        duration_ms = round(samples / 16)
        text,words,fixups=recognize(MODEL,audio,duration_ms,True)
        # Retry only audible input. Never turn a silent recording into an answer.
        if not text and signal['rms']>=0.0005 and signal['peak']>=0.003 and signal['active_ratio']>=0.02:
            text,words,fixups=recognize(MODEL,audio,duration_ms,False)
            fallback=True
            warnings.append('语音检测未给出转写，已尝试不裁剪音频；请仔细确认识别文字，噪声也可能造成误识别。')
    except Exception:
        raise HTTPException(503, '本地语音识别失败，请稍后重试或联系教师检查模型安装')
    if not text:
        raise HTTPException(400,'服务器已收到'+str(round(samples/16000,1))+'秒录音，输入音量约'+str(signal['dbfs'])+' dBFS，但识别器未能转写。请先回听：若无自己的声音，切换麦克风；若声音清楚，可上传同一段音频排查模型。')
    if len(text) > 2000:
        raise HTTPException(400, '识别文本过长，请缩短录音')
    timed=bool(words)
    if not timed:warnings.append('识别到文字但缺少词级时间戳，本轮不计算语速或停顿。')
    tokens=words if timed else [{'w':w} for w in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",text)]
    metrics = analyse(tokens).as_columns()
    # This is silence after pressing record, NOT conversational response latency.
    metrics['leading_silence_ms'] = metrics.pop('response_latency_ms')
    return {'text': text, 'metrics': metrics, 'words': words, 'duration_ms': duration_ms,
            'timestamp_fixups': fixups, 'signal':signal, 'gain':round(max(1.0,gain),2),'vad_retry':fallback,'timing_available':timed,'warnings':warnings,'asr_version':'1.4.1', 'model': 'faster-whisper/tiny.en:int8', 'pause_threshold_ms': 300}


def signal_info(audio):
    import numpy as np
    rms=float(np.sqrt(np.mean(audio*audio,dtype=np.float64)))
    peak=float(np.max(np.abs(audio)))
    size=1600
    frames=[audio[i:i+size] for i in range(0,len(audio),size)]
    active=sum(float(np.sqrt(np.mean(f*f,dtype=np.float64)))>=0.0005 for f in frames)
    return {'rms':round(rms,7),'peak':round(peak,7),'dbfs':round(20*math.log10(max(rms,1e-9)),1),'active_ratio':round(active/max(len(frames),1),3)}


def recognize(model,audio,duration_ms,use_vad):
    options={'language':'en','beam_size':3 if use_vad else 5,'word_timestamps':True,
             'vad_filter':use_vad,'condition_on_previous_text':False,
             'no_speech_threshold':0.6}
    if use_vad:options['vad_parameters']={'threshold':0.35,'min_speech_duration_ms':100,'min_silence_duration_ms':500,'speech_pad_ms':200}
    segments,_=model.transcribe(audio,**options)
    words,texts,fixups=[],[],0
    for segment in segments:
        texts.append(segment.text)
        for word in segment.words or []:
            original=(round(word.start*1000),round(word.end*1000))
            start=min(duration_ms,max(0,original[0]));end=min(duration_ms,max(start,original[1]))
            fixups+=(start,end)!=original
            words.append({'w':word.word.strip(),'start_ms':start,'end_ms':end})
    return ''.join(texts).strip(),words,fixups
