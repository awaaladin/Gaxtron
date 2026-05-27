"""Structured logging of agent decisions for production observability."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.models.schemas import AgentDecisionLog, AgentRunResult

logger = logging.getLogger("gaxtron.agent")


class AgentDecisionLogger:
    """Logs agent reasoning, tool usage, and decisions to stdout + optional file."""

    def __init__(self, log_dir: str | None = None):
        self._decisions: list[AgentDecisionLog] = []
        self._log_dir = Path(log_dir) if log_dir else None
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def decisions(self) -> list[AgentDecisionLog]:
        return list(self._decisions)

    def log(self, phase: str, message: str, **data: Any) -> AgentDecisionLog:
        entry = AgentDecisionLog(
            phase=phase,
            message=message,
            data=data,
            timestamp=datetime.now(timezone.utc),
        )
        self._decisions.append(entry)
        logger.info(
            "[AGENT:%s] %s | %s",
            phase,
            message,
            json.dumps(data, default=str) if data else "",
        )
        return entry

    def persist_run(self, run: AgentRunResult) -> str | None:
        if not self._log_dir:
            return None
        path = self._log_dir / f"{run.run_id}.json"
        payload = run.model_dump(mode="json")
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.info("Agent run persisted: %s", path)
        return str(path)
