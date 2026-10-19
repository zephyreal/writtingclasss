"""Real audio decoding with a fake recognizer; no model downloads or paid API."""
import io
import math
import sys
import types
import wave
import pytest
import numpy as np
from fastapi import HTTPException
import english_speech as speech


def wav(seconds=2,amplitude=8000,rate=16000,channels=1):
    data=np.array([int(amplitude*math.sin(2*math.pi*220*i/rate)) for i in range(int(seconds*rate))],dtype='<i2')
    if channels==2:data=np.column_stack((data,data)).reshape(-1)
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(channels);w.setsampwidth(2);w.setframerate(rate);w.writeframes(data.tobytes())
    return out.getvalue()


def segment(text=' Hello, I am a student.',timed=True):
    return types.SimpleNamespace(text=text,words=[types.SimpleNamespace(word='Hello',start=.1,end=.4),types.SimpleNamespace(word='student',start=.8,end=1.1)] if timed else [])


@pytest.fixture
def setup(monkeypatch,tmp_path):
    (tmp_path/'english-asr').mkdir();(tmp_path/'english-asr/READY').write_text('test')
    fake=types.ModuleType('faster_whisper');fake.WhisperModel=lambda *args,**kwargs:None
    monkeypatch.setitem(sys.modules,'faster_whisper',fake)
    monkeypatch.setattr(speech,'MODEL',None)
    return tmp_path


def test_real_stereo_resampling_and_word_metrics(monkeypatch,setup):
    seen=[]
    class Model:
        def transcribe(self,audio,**options):seen.append((len(audio),options));return iter([segment()]),None
    monkeypatch.setattr(speech,'MODEL',Model())
    r=speech.transcribe(wav(rate=44100,channels=2),setup)
    assert r['text'].startswith('Hello') and 1990<=r['duration_ms']<=2010
    assert seen[0][0] in range(31900,32100) and seen[0][1]['vad_parameters']['threshold']==.35
    assert .1<r['signal']['rms']<.3 and r['timing_available'] and r['metrics']['speech_rate_wpm'] is not None


def test_empty_vad_retries_audible_audio_without_cropping(monkeypatch,setup):
    calls=[]
    class Model:
        def transcribe(self,audio,**options):
            calls.append(options)
            return iter([] if options['vad_filter'] else [segment()]),None
    monkeypatch.setattr(speech,'MODEL',Model())
    r=speech.transcribe(wav(),setup)
    assert r['vad_retry'] and [x['vad_filter'] for x in calls]==[True,False]
    assert calls[1]['no_speech_threshold']==.6 and r['warnings']


def test_silence_rejected_before_model_and_lock_released(monkeypatch,setup):
    class Model:
        def transcribe(self,*args,**kwargs):pytest.fail('silent recording must not generate text')
    monkeypatch.setattr(speech,'MODEL',Model())
    for _ in range(2):
        with pytest.raises(HTTPException) as error:speech.transcribe(wav(amplitude=0),setup)
        assert error.value.status_code==400 and '接近静音' in error.value.detail


def test_valid_text_without_word_timings_does_not_invent_rates(monkeypatch,setup):
    class Model:
        def transcribe(self,*args,**kwargs):return iter([segment(timed=False)]),None
    monkeypatch.setattr(speech,'MODEL',Model())
    r=speech.transcribe(wav(),setup)
    assert r['text'] and not r['timing_available']
    assert r['metrics']['word_count']==5 and r['metrics']['speech_rate_wpm'] is None and r['metrics']['pause_ratio'] is None


def test_empty_result_has_audio_diagnostics_instead_of_claiming_no_english(monkeypatch,setup):
    class Model:
        def transcribe(self,*args,**kwargs):return iter([]),None
    monkeypatch.setattr(speech,'MODEL',Model())
    with pytest.raises(HTTPException) as e:speech.transcribe(wav(),setup)
    assert '2.0秒' in e.value.detail and 'dBFS' in e.value.detail and '切换麦克风' in e.value.detail


def test_quiet_audio_gain_is_bounded(monkeypatch,setup):
    peaks=[]
    class Model:
        def transcribe(self,audio,**kwargs):peaks.append(float(np.max(np.abs(audio))));return iter([segment()]),None
    monkeypatch.setattr(speech,'MODEL',Model())
    r=speech.transcribe(wav(amplitude=12),setup)
    assert 1<r['gain']<=8 and peaks[0]<=r['signal']['peak']*8+.00001


def test_bad_and_overlong_audio_are_rejected_without_model(monkeypatch,setup):
    class Model:
        def transcribe(self,*args,**kwargs):pytest.fail('invalid audio must not reach recognizer')
    monkeypatch.setattr(speech,'MODEL',Model())
    with pytest.raises(HTTPException) as e:speech.transcribe(b'not audio',setup)
    assert e.value.status_code==400
    with pytest.raises(HTTPException) as e:speech.transcribe(wav(seconds=61),setup)
    assert e.value.status_code==413
