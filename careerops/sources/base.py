from __future__ import annotations
from abc import ABC, abstractmethod

class JobSource(ABC):
    @abstractmethod
    async def fetch(self) -> list[dict]: ...
