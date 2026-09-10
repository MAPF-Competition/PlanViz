"""Wall-clock playback; logical state is independent of rendered frames."""
from __future__ import annotations

import math
import time
from PySide6.QtCore import QObject, QTimer, Qt, Signal


class PlaybackController(QObject):
    timeChanged = Signal(int)
    frameRequested = Signal(float)
    playingChanged = Signal(bool)
    rangeChanged = Signal(int, int)

    def __init__(self, parent=None, fps: int = 60):
        super().__init__(parent)
        self.start = self.end = self.time = 0
        self.position = 0.0
        self.speed = 5.0
        self._last_clock = 0.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(max(1, round(1000 / max(1, fps))))
        self.timer.timeout.connect(self._advance)

    @property
    def playing(self) -> bool:
        return self.timer.isActive()

    def configure(self, start: int, end: int, speed: float | None = None):
        self.pause()
        self.start, self.end = max(0, int(start)), max(0, int(end))
        if self.end < self.start:
            self.start = self.end
        if speed is not None:
            self.set_speed(speed)
        self.rangeChanged.emit(self.start, self.end)
        self.seek(self.start)

    def set_speed(self, speed: float):
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("Playback speed must be finite and positive")
        if self.playing:
            # Account for elapsed time at the old rate before changing it.
            self._advance()
        self.speed = float(speed)

    def seek(self, target: int, *, pause: bool = True):
        if pause:
            self.pause()
        self.time = min(self.end, max(self.start, int(target)))
        self.position = float(self.time)
        self._last_clock = time.perf_counter()
        self.timeChanged.emit(self.time)
        self.frameRequested.emit(self.position)

    def step(self, delta: int):
        self.seek(self.time + delta)

    def toggle(self):
        self.pause() if self.playing else self.play()

    def play(self):
        if self.end <= self.start:
            return
        if self.time >= self.end:
            self.seek(self.start)
        self._last_clock = time.perf_counter()
        self.timer.start()
        self.playingChanged.emit(True)

    def pause(self):
        was_playing = self.playing
        self.timer.stop()
        if was_playing:
            self.playingChanged.emit(False)

    def _advance(self):
        now = time.perf_counter()
        elapsed = max(0.0, now - self._last_clock)
        self._last_clock = now
        self.advance_seconds(elapsed)

    def advance_seconds(self, elapsed: float):
        """Advance from elapsed time, also useful for deterministic verification."""
        self.position = min(float(self.end), self.position + max(0, elapsed) * self.speed)
        logical_time = min(self.end, math.floor(self.position))
        if logical_time != self.time:
            self.time = logical_time
            self.timeChanged.emit(self.time)
        self.frameRequested.emit(self.position)
        if self.position >= self.end:
            self.pause()
