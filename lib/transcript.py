from dataclasses import dataclass
from typing import List


@dataclass
class Segment:
    text: str
    start: float
    duration: float


@dataclass
class Sentence:
    text: str
    segments: List[Segment]

    @property
    def start_time(self) -> float:
        return self.segments[0].start

    @property
    def end_time(self) -> float:
        return self.segments[-1].start + self.segments[-1].duration
