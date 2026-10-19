"""Fluency from word timings: how fast, how broken up, how hesitant.

Everything here is arithmetic over `turns.words`. No model reads a transcript to decide
whether somebody sounded fluent — the same recording produces the same six numbers on
every rebuild, which is what makes them safe to plot over months.

**Speech rate and articulation rate are kept apart deliberately.** A speaker who gets
faster only by pausing less has not learned to articulate any faster, and one number
covering both reports that as progress. Speech rate spends the pauses; articulation rate
removes them. Both are words per minute so they can be read against each other.

**One definition of a pause, used by three metrics.** A gap of at least
`FLUENCY_PAUSE_MS` between the end of one word and the start of the next. Every gap
smaller than that is treated as continuous speech, because word boundaries from the
recogniser are only accurate to a few tens of milliseconds and summing every small gap
would mostly measure its timestamp granularity. Articulation rate, pause ratio and mean
length of run all use this one rule, so they cannot disagree about what a pause is.

**The span, not the file.** Duration runs from the start of the first word to the end of
the last. Leading and trailing silence is the recorder — somebody reaching for a button —
and counting it as pausing would make a speaker look hesitant for being slow with a
mouse. The leading silence is kept separately, and named for what it is.

**Filler counting undercounts, twice over, and both are worth knowing.** The recogniser
is trained on cleaned transcripts and drops most `um`s before this code ever sees them;
and bare `like` is not counted at all, because "like a dog or a cat" is an ordinary
preposition and no rule over a word list can tell it from the discourse marker. So this
number is a floor. It moves when somebody is dysfluent enough to survive the recogniser,
and it is never evidence that a speaker had no fillers.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

FLUENCY_PAUSE_MS = 300  # Local course setting; upstream imports this from config.

# Closed list, and closed on purpose. These survive the recogniser as literal tokens.
# `like` and `you know` are the two the requirements also name, and neither is here:
# both have ordinary uses that a word list cannot separate from the disfluent one, and a
# metric that scores "I want to know more" as hesitation is worse than one that misses a
# real filler.
FILLERS: frozenset[str] = frozenset(
    {"um", "umm", "uh", "uhh", "er", "erm", "eh", "mm", "mmm", "hmm", "hm", "ah"}
)

_STRIP = re.compile(r"^[^\w']+|[^\w']+$")


@dataclass(frozen=True)
class Fluency:
    """The six stored numbers, plus the two counts they are derived from."""

    word_count: int

    # Words per minute across the whole speaking span, pauses included.
    speech_rate_wpm: float | None

    # Words per minute across phonated time only. Never lower than speech rate.
    articulation_rate: float | None

    # Share of the speaking span spent in pauses of at least FLUENCY_PAUSE_MS.
    pause_ratio: float | None

    # Mean words between those pauses. One long unbroken answer and one delivered in
    # six-word bursts can share a speech rate and differ entirely here.
    mean_length_run: float | None

    filler_count: int

    # Silence before the first word of the recording. This is a floor on the real
    # response latency and not the same measurement: the clock starts when the speaker
    # pressed record, not when the persona stopped speaking. Measuring the gap the
    # requirements describe needs the browser to timestamp the button against the end of
    # the reply audio, which nothing does today.
    response_latency_ms: int | None

    def as_columns(self) -> dict:
        return asdict(self)


def analyse(words: list[dict] | None) -> Fluency:
    """Every metric for one turn. Never raises; a turn with no timings gives nulls.

    A turn can legitimately arrive with no words — silence, or a recording the recogniser
    found nothing in. That is a turn with no fluency to measure, not a turn with a
    fluency of zero, so the rates are null and only the counts are real.
    """
    usable = [w for w in (words or []) if _timed(w)]
    if not usable:
        return Fluency(
            word_count=len(words or []),
            speech_rate_wpm=None,
            articulation_rate=None,
            pause_ratio=None,
            mean_length_run=None,
            filler_count=_fillers(words or []),
            response_latency_ms=None,
        )

    count = len(usable)
    started = int(usable[0]["start_ms"])
    ended = max(int(w["end_ms"]) for w in usable)
    span_ms = ended - started

    pauses = [
        gap
        for gap in (
            int(nxt["start_ms"]) - int(cur["end_ms"])
            for cur, nxt in zip(usable, usable[1:])
        )
        if gap >= FLUENCY_PAUSE_MS
    ]
    paused_ms = sum(pauses)
    phonated_ms = span_ms - paused_ms

    return Fluency(
        word_count=count,
        speech_rate_wpm=_wpm(count, span_ms),
        articulation_rate=_wpm(count, phonated_ms),
        # A one-word turn has no span and no pauses; 0.0 says "none", which is true,
        # where None would say "not measured", which is not.
        pause_ratio=round(paused_ms / span_ms, 4) if span_ms > 0 else 0.0,
        mean_length_run=round(count / (len(pauses) + 1), 3),
        filler_count=_fillers(usable),
        response_latency_ms=started,
    )


def _timed(word: object) -> bool:
    """Whether a stored word carries usable timings.

    The column is JSONB and a stored row may lack a key, so a missing one is a real
    possibility rather than a defensive habit. A word with an end before its start is
    discarded too: the recogniser corrects those itself and counts the corrections, but a
    stored row may predate that.
    """
    if not isinstance(word, dict):
        return False
    start, end = word.get("start_ms"), word.get("end_ms")
    if not isinstance(start, int) or not isinstance(end, int):
        return False
    return 0 <= start <= end


def _wpm(count: int, duration_ms: int) -> float | None:
    if duration_ms <= 0:
        return None
    return round(count * 60000 / duration_ms, 2)


def _fillers(words: list[dict]) -> int:
    tokens = [
        _STRIP.sub("", str(word.get("w", "")).lower())
        for word in words
        if isinstance(word, dict)
    ]
    return sum(1 for token in tokens if token in FILLERS)
