from dataclasses import dataclass
from typing import Tuple


@dataclass
class TemplateMatchResult:
    target_score: float
    score: float
    bounds: Tuple[float, float, float, float]
    result_code: int

    @property
    def center(self) -> Tuple[float, float]:
        return (self.bounds[0] + self.bounds[2]) / 2, (self.bounds[1] + self.bounds[3]) / 2

    @property
    def size(self) -> Tuple[float, float]:
        return self.bounds[2] - self.bounds[0], self.bounds[3] - self.bounds[1]

    @property
    def success(self) -> bool:
        return self.result_code == 0

    def __bool__(self):
        return self.success

    def __str__(self):
        return f'TemplateMatchResult: {self.success}, {self.score:.2%}, {self.bounds}, {self.center}'


class TemplateMatchError(Exception):
    def __init__(self, message: str, match_result: TemplateMatchResult):
        super().__init__(message)
        self.message = message
        self.match_result = match_result
