"""MCP-style tool base for agent systems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.agents.models.schemas import ToolResult


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult: ...
