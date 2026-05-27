"""
Gaxtron Payment Orchestrator — Track 3 architecture.

Event-driven state machine for blockchain payment routing.
Designed for Google Cloud Marketplace & Gemini Enterprise deployment.

NOT a shared/generic agent framework — Gaxtron-team owned.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from app.agents.models.schemas import AgentDecisionLog, AgentGoal, AgentRunResult
from app.agents.tools.payment_tools import (
    ChainHealthTool,
    ChainSelectionTool,
    FeeOptimizationTool,
    FraudDetectionTool,
    PaymentExecutionTool,
    PaymentVerificationTool,
)

logger = logging.getLogger("gaxtron.orchestrator")


class PaymentEvent(str, Enum):
    """Event-driven pipeline states — Track 3 production pattern."""

    RECEIVED = "payment_received"
    NETWORK_ANALYZED = "network_analyzed"
    RISK_CLEARED = "risk_cleared"
    ROUTE_OPTIMIZED = "route_optimized"
    CHAIN_SELECTED = "chain_selected"
    EXECUTED = "executed"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass
class PaymentContext:
    """Gaxtron-specific execution context (not a generic agent memory)."""

    goal: str
    amount: str
    callback_url: str
    user_id: int
    currency_preference: str = "ETH"
    idempotency_key: str | None = None
    recent_payment_count: int = 0
    artifacts: dict[str, Any] = field(default_factory=dict)
    current_event: PaymentEvent = PaymentEvent.RECEIVED
    event_history: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[AgentDecisionLog] = field(default_factory=list)

    def emit(self, event: PaymentEvent, detail: str, **data: Any) -> None:
        self.current_event = event
        entry = {"event": event.value, "detail": detail, "timestamp": datetime.now(timezone.utc).isoformat(), **data}
        self.event_history.append(entry)
        self.decisions.append(AgentDecisionLog(phase=event.value, message=detail, data=data))
        logger.info("[GAXTRON:%s] %s", event.value, detail)

    def to_params(self) -> dict[str, Any]:
        params = {
            "amount": self.amount,
            "callback_url": self.callback_url,
            "user_id": self.user_id,
            "currency_preference": self.currency_preference,
            "idempotency_key": self.idempotency_key,
            "recent_payment_count": self.recent_payment_count,
        }
        params.update(self.artifacts)
        return params


@dataclass
class OrchestratorStep:
    event: PaymentEvent
    tool_name: str
    artifact_key: str
    on_failure: PaymentEvent = PaymentEvent.FAILED


class GaxtronPaymentOrchestrator:
    """
    Track 3: Refactor for Google Cloud Marketplace.

    Event-driven orchestrator with MCP-connected blockchain tools.
    Replaces generic planner/executor loop with production state machine.
    """

    AGENT_NAME = "gaxtron_payment_orchestrator"
    TRACK = "Track 3 — Refactor for Google Cloud Marketplace & Gemini Enterprise"

    PIPELINE: list[OrchestratorStep] = [
        OrchestratorStep(PaymentEvent.NETWORK_ANALYZED, "chain_health_check", "analyze_payment"),
        OrchestratorStep(PaymentEvent.RISK_CLEARED, "fraud_detection", "fraud_detection"),
        OrchestratorStep(PaymentEvent.ROUTE_OPTIMIZED, "fee_optimizer", "fee_optimizer"),
        OrchestratorStep(PaymentEvent.CHAIN_SELECTED, "chain_selector", "chain_selector"),
        OrchestratorStep(PaymentEvent.EXECUTED, "payment_executor", "payment_executor"),
        OrchestratorStep(PaymentEvent.VERIFIED, "payment_verifier", "payment_verifier"),
    ]

    def __init__(self, db, log_dir: str | None = None):
        self._db = db
        self._log_dir = log_dir
        self._tools = {
            "chain_health_check": ChainHealthTool(),
            "fraud_detection": FraudDetectionTool(),
            "fee_optimizer": FeeOptimizationTool(),
            "chain_selector": ChainSelectionTool(),
            "payment_executor": PaymentExecutionTool(db),
            "payment_verifier": PaymentVerificationTool(),
        }

    def run(self, goal: AgentGoal) -> AgentRunResult:
        run_id = f"gax_{uuid.uuid4().hex[:12]}"
        started = datetime.now(timezone.utc)

        ctx = PaymentContext(
            goal=goal.description,
            amount=str(goal.context.get("amount", "")),
            callback_url=str(goal.context.get("callback_url", "")),
            user_id=int(goal.context.get("user_id", 0)),
            currency_preference=str(goal.context.get("currency_preference", "ETH")),
            idempotency_key=goal.context.get("idempotency_key"),
            recent_payment_count=int(goal.context.get("recent_payment_count", 0)),
        )
        ctx.emit(PaymentEvent.RECEIVED, f"Payment goal received: {goal.description}")

        steps = []
        failed = False

        for stage in self.PIPELINE:
            tool = self._tools[stage.tool_name]
            params = ctx.to_params()
            result = None

            for attempt in range(1, 3):
                start = time.perf_counter()
                try:
                    result = tool.execute(**params)
                    result.duration_ms = (time.perf_counter() - start) * 1000
                except Exception as exc:
                    from app.agents.models.schemas import ToolResult
                    result = ToolResult(success=False, error=str(exc))

                if result.success:
                    break
                ctx.emit(
                    PaymentEvent.FAILED,
                    f"{stage.tool_name} attempt {attempt} failed: {result.error}",
                    tool=stage.tool_name,
                    attempt=attempt,
                )

            if result and result.success:
                ctx.artifacts[stage.artifact_key] = result.output
                ctx.emit(stage.event, f"{stage.tool_name} succeeded", tool=stage.tool_name, output_keys=list(result.output.keys()))
            else:
                ctx.emit(stage.on_failure, f"{stage.tool_name} failed: {result.error if result else 'unknown'}", tool=stage.tool_name)
                failed = True
                if result:
                    from app.agents.models.schemas import StepResult
                    steps.append(
                        StepResult(
                            task_id=stage.artifact_key,
                            task_name=stage.artifact_key,
                            tool_name=stage.tool_name,
                            result=result,
                            reasoning=f"Failed: {stage.event.value}",
                        )
                    )
                break

            from app.agents.models.schemas import StepResult
            steps.append(
                StepResult(
                    task_id=stage.artifact_key,
                    task_name=stage.artifact_key,
                    tool_name=stage.tool_name,
                    result=result,
                    reasoning=f"Event: {stage.event.value}",
                )
            )

        status = "completed" if not failed and ctx.current_event == PaymentEvent.VERIFIED else ("failed" if failed else "partial")
        final_score = 1.0 if status == "completed" else 0.0

        from app.agents.models.schemas import AgentPlan, AgentTask, EvaluationResult

        run = AgentRunResult(
            run_id=run_id,
            agent_name=self.AGENT_NAME,
            goal=goal.description,
            status=status,
            plan=AgentPlan(
                goal=goal.description,
                tasks=[AgentTask(name=s.task_name, description=s.reasoning, tool_name=s.tool_name) for s in steps],
                reasoning=f"Gaxtron event-driven pipeline ({self.TRACK})",
            ),
            steps=steps,
            evaluations=[EvaluationResult(passed=status == "completed", score=final_score, feedback=f"Final event: {ctx.current_event.value}")],
            decisions=ctx.decisions,
            final_output={**ctx.artifacts, "event_history": ctx.event_history, "track": self.TRACK},
            started_at=started,
            completed_at=datetime.now(timezone.utc),
        )

        if self._log_dir:
            from app.agents.core.logger import AgentDecisionLogger
            AgentDecisionLogger(log_dir=self._log_dir).persist_run(run)

        return run


# Backward-compatible alias for existing imports
PaymentRoutingAgent = GaxtronPaymentOrchestrator
