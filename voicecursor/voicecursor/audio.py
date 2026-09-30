"""Microphone capture."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Iterator

log = logging.getLogger(__name__)


def list_devices() -> None:
    import sounddevice as sd
    print(sd.query_devices())


class MicStream:
    """16-bit mono PCM from the microphone, exposed as an iterator of byte chunks.

    The audio callback only enqueues; all recognition work happens on the
    consumer's thread. The queue is bounded: if the consumer falls behind we
    drop audio rather than let latency grow without limit.
    """

    def __init__(self, sample_rate: int = 16_000, block_ms: int = 100,
                 device: int | str | None = None, max_blocks: int = 50) -> None:
        self.sample_rate = sample_rate
        self.blocksize = sample_rate * block_ms // 1000
        self.device = device
        self._q: queue.Queue[bytes] = queue.Queue(maxsize=max_blocks)
        self._stream = None

    def __enter__(self) -> "MicStream":
        import sounddevice as sd
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate, blocksize=self.blocksize, device=self.device,
            dtype="int16", channels=1, callback=self._on_audio)
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            log.warning("audio status: %s", status)
        try:
            self._q.put_nowait(bytes(indata))
        except queue.Full:
            log.warning("recogniser is falling behind; dropping an audio block")

    def chunks(self, stop: threading.Event) -> Iterator[bytes]:
        while not stop.is_set():
            try:
                yield self._q.get(timeout=0.2)
            except queue.Empty:
                continue
