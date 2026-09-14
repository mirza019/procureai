from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AIResponse:
    text: str
    provider: str
    model: str
    usage: dict[str, int] | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, evidence: Mapping[str, Any]) -> AIResponse:
        """Generate advisory prose from trusted structured evidence."""
