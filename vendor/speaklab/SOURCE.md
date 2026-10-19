# SpeakLab reuse

- Upstream: https://github.com/Luisfelipecruz/speaklab
- Commit: `3c9ba3c45f5a42340c981aa08d8d73b2433515b3`
- License: MIT, Copyright (c) 2026 Luis Cruz. Full notice in `LICENSE`.
- `fluency.py` is copied from `api/services/fluency.py`; only the config import is
  replaced with a local 300 ms pause threshold. Formulae and null semantics retained.
- `scenarios.json` is the unchanged `api/seeds/scenarios.json`. The course supplies
  Chinese display titles and a simplified conversation contract; upstream CEFR tags
  are not treated as students' proficiency measurements.
- `../../english_speech.py` adapts PyAV mono resampling, decoded-sample duration,
  word timestamp normalization, English-only ASR, VAD and no previous-text
  conditioning from `infra/asr/app.py`. Differences: integrated authenticated API,
  maximum 60 seconds enforced during decoding, no retained audio, tiny.en CPU int8,
  single inference lock and local-only model loading after explicit installation.

The upstream five-container stack, Ollama, Piper and optional phoneme GOP scorer
are not installed. No claim is made that transcript timings measure pronunciation.
`response_latency_ms` is exposed as `leading_silence_ms` to avoid confusing the
button-to-speech interval with conversational response latency.

`wikibit888/oral` was reviewed for architecture but its code is not incorporated:
no explicit license was found at the time of this integration.
