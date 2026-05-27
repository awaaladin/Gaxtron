"""Agent API — goal-driven autonomous execution endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from app.agents.gcp.marketplace import MARKETPLACE_LISTING, READINESS_CHECKLIST
from app.agents.mcp.blockchain_mcp import get_mcp_manifest
from app.agents.models.schemas import AgentGoal, AgentRunResult
from app.agents.payment_routing_agent import PaymentRoutingAgent
from app.api.deps import get_current_user_api_key
from app.db.models.payment import Payment
from app.db.models.user import User
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


class PaymentAgentGoalRequest(BaseModel):
    """Goal-driven payment request — not a prompt."""

    goal: str = Field(
        ...,
        min_length=5,
        examples=["Process crypto payment with lowest fees and fastest confirmation"],
    )
    amount: str = Field(..., examples=["0.01"])
    callback_url: HttpUrl
    currency_preference: str = Field(default="ETH", examples=["ETH", "USDT", "SOL"])
    idempotency_key: str | None = None


class AgentRunResponse(BaseModel):
    run_id: str
    agent_name: str
    goal: str
    status: str
    reasoning_chain: list[str]
    tool_usage: list[dict]
    plan_summary: str
    tasks_completed: int
    tasks_total: int
    final_score: float
    payment: dict | None = None
    decisions: list[dict]
    started_at: datetime
    completed_at: datetime | None


def _serialize_run(run: AgentRunResult) -> AgentRunResponse:
    tool_usage = [
        {
            "task": s.task_name,
            "tool": s.tool_name,
            "success": s.result.success,
            "duration_ms": s.result.duration_ms,
            "output_keys": list(s.result.output.keys()),
        }
        for s in run.steps
    ]
    reasoning = [d.message for d in run.decisions]
    final_score = run.evaluations[-1].score if run.evaluations else 0.0
    payment = run.final_output.get("payment_executor")

    return AgentRunResponse(
        run_id=run.run_id,
        agent_name=run.agent_name,
        goal=run.goal,
        status=run.status,
        reasoning_chain=reasoning,
        tool_usage=tool_usage,
        plan_summary=run.plan.reasoning,
        tasks_completed=sum(1 for s in run.steps if s.result.success),
        tasks_total=len(run.plan.tasks),
        final_score=final_score,
        payment=payment if isinstance(payment, dict) else None,
        decisions=[d.model_dump(mode="json") for d in run.decisions],
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.post("/payment/route", response_model=AgentRunResponse)
def route_payment(
    body: PaymentAgentGoalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api_key),
):
    """
    Gaxtron Track 3 — Event-driven payment orchestrator.

    Flow: Goal → Network Analysis → Risk Clear → Route Optimize → Chain Select → Execute → Verify
    """
    since = datetime.utcnow() - timedelta(hours=1)
    recent_count = (
        db.query(Payment)
        .filter(Payment.user_id == user.id, Payment.created_at >= since)
        .count()
    )

    goal = AgentGoal(
        description=body.goal,
        context={
            "amount": body.amount,
            "callback_url": str(body.callback_url),
            "currency_preference": body.currency_preference,
            "user_id": user.id,
            "idempotency_key": body.idempotency_key,
            "recent_payment_count": recent_count,
        },
    )

    agent = PaymentRoutingAgent(db=db, log_dir="logs/agents")
    run = agent.run(goal)
    return _serialize_run(run)


@router.get("/payment/runs/{run_id}")
def get_agent_run_info(run_id: str):
    """Retrieve persisted agent run log if available."""
    from pathlib import Path
    import json

    path = Path("logs/agents") / f"{run_id}.json"
    if not path.is_file():
        return {"run_id": run_id, "found": False}
    return {"run_id": run_id, "found": True, "run": json.loads(path.read_text(encoding="utf-8"))}


@router.get("/mcp/manifest")
def mcp_manifest():
    """MCP tool manifest for Gemini Enterprise / external agent connections."""
    return get_mcp_manifest()


@router.get("/payment/demo")
def payment_agent_demo(db: Session = Depends(get_db)):
    """Run full payment orchestrator pipeline (no auth — demo only)."""
    goal = AgentGoal(
        description="Process crypto payment with lowest fees and fastest confirmation",
        context={
            "amount": "0.01",
            "callback_url": "https://example.com/webhook",
            "user_id": 1,
            "currency_preference": "ETH",
            "recent_payment_count": 0,
        },
    )
    run = PaymentRoutingAgent(db=db, log_dir=None).run(goal)
    return _serialize_run(run)


@router.get("/gcp/readiness")
def gcp_readiness():
    """Google Cloud Marketplace readiness checklist."""
    return {"listing": MARKETPLACE_LISTING, "readiness": READINESS_CHECKLIST}
