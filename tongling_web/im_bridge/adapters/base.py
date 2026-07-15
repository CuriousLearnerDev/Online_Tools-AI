from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ImAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def stop(self) -> None:
        pass

    @abstractmethod
    def status(self) -> Dict[str, Any]:
        pass

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        return None
