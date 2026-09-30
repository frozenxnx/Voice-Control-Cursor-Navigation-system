"""Grammar-constrained speech recognition with Vosk."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .commands import Mode
from .parser import vocabulary

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Hypothesis:
    text: str
    final: bool  # False = partial result, may still change


class VoskRecognizer:
    """One KaldiRecognizer per Mode, each restricted to that mode's vocabulary.

    Restricting the vocabulary is what makes command recognition fast and
    accurate. Note: runtime grammars require a model with a dynamic graph,
    i.e. the *small* Vosk models (vosk-model-small-*). The large static-graph
    models ignore the grammar.
    """

    def __init__(self, model_path: str, sample_rate: int = 16_000) -> None:
        try:
            import vosk
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Vosk is not installed: pip install vosk") from exc
        if not Path(model_path).is_dir():
            raise FileNotFoundError(
                f"Vosk model not found at '{model_path}'. Download a small model from "
                "https://alphacephei.com/vosk/models and pass --model <folder>.")
        vosk.SetLogLevel(-1)
        self._vosk = vosk
        self._model = vosk.Model(model_path)
        self._rate = sample_rate
        self._recognizers: dict[Mode, object] = {}
        self._active: Mode | None = None

    def _recognizer_for(self, mode: Mode):
        rec = self._recognizers.get(mode)
        if rec is None:
            rec = self._vosk.KaldiRecognizer(
                self._model, self._rate, json.dumps(vocabulary(mode)))
            self._shorten_endpointing(rec)
            self._recognizers[mode] = rec
        return rec

    def _shorten_endpointing(self, rec) -> None:
        """Ask Vosk to finalise sooner after you stop talking (lower latency).
        Only available in newer Vosk builds; harmless if missing."""
        try:
            rec.SetEndpointerMode(self._vosk.EndpointerMode.SHORT)
        except Exception:  # noqa: BLE001 - optional feature
            log.debug("Vosk endpointer tuning unavailable in this version")

    def feed(self, mode: Mode, data: bytes) -> Hypothesis | None:
        """Feed one audio chunk. Returns a final Hypothesis when an utterance
        ends, a partial one while speech is in progress, else None."""
        if mode is not self._active:
            if self._active is not None:
                self._recognizers[self._active].Reset()  # drop stale audio state
            self._active = mode
        rec = self._recognizer_for(mode)
        if rec.AcceptWaveform(data):
            return Hypothesis(json.loads(rec.Result()).get("text", ""), final=True)
        partial = json.loads(rec.PartialResult()).get("partial", "")
        return Hypothesis(partial, final=False) if partial else None
