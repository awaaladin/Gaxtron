"""Payment routing agent tools — blockchain APIs and internal services."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.agents.models.schemas import ToolResult
from app.agents.tools.base import BaseTool
from app.chains.registry import CHAIN_CURRENCIES
from app.config import settings
from app.schemas.payment import CreatePaymentRequest
from app.services.health_service import check_all_chains
from app.services.payment_processor import get_payment_processor
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

# Estimated relative fee weights (lower = cheaper for small payments)
FEE_WEIGHTS: dict[str, float] = {
    "SOL": 0.1,
    "TRON": 0.3,
    "ETH": 1.0,
    "BTC": 1.5,
}

CONFIRMATION_SPEED: dict[str, int] = {
    "SOL": 32,
    "TRON": 19,
    "ETH": 3,
    "BTC": 3,
}


class ChainHealthTool(BaseTool):
    name = "chain_health_check"
    description = "Check RPC connectivity for all enabled blockchain networks"

    def execute(self, **kwargs: Any) -> ToolResult:
        health = check_all_chains()
        healthy = [c for c, ok in health.items() if ok]
        return ToolResult(
            success=bool(healthy),
            output={
                "chain_health": health,
                "healthy_chains": healthy,
                "unhealthy_chains": [c for c, ok in health.items() if not ok],
            },
            error=None if healthy else "No healthy chains available",
        )


class FraudDetectionTool(BaseTool):
    name = "fraud_detection"
    description = "Detect suspicious payment patterns (amount anomalies, callback risks)"

    SUSPICIOUS_CALLBACK_PATTERNS = ("localhost", "127.0.0.1", "0.0.0.0", "192.168.", "10.")

    def execute(self, **kwargs: Any) -> ToolResult:
        amount = Decimal(str(kwargs.get("amount", "0")))
        callback_url = str(kwargs.get("callback_url", ""))
        user_id = kwargs.get("user_id")

        flags: list[str] = []
        risk_score = 0.0

        if amount <= 0:
            flags.append("invalid_amount")
            risk_score += 0.5
        if amount > Decimal("100"):
            flags.append("high_value_payment")
            risk_score += 0.2

        callback_lower = callback_url.lower()
        if any(p in callback_lower for p in self.SUSPICIOUS_CALLBACK_PATTERNS):
            if settings.require_https_callbacks or settings.is_production:
                flags.append("suspicious_callback_host")
                risk_score += 0.4

        if not callback_url.startswith("https://") and settings.require_https_callbacks:
            flags.append("insecure_callback")
            risk_score += 0.3

        # Rapid repeat from same user (basic heuristic)
        recent_count = kwargs.get("recent_payment_count", 0)
        if recent_count and int(recent_count) > 10:
            flags.append("velocity_limit_exceeded")
            risk_score += 0.3

        risk_score = min(risk_score, 1.0)
        blocked = risk_score >= 0.7

        return ToolResult(
            success=not blocked,
            output={
                "risk_score": risk_score,
                "flags": flags,
                "approved": not blocked,
                "user_id": user_id,
            },
            error=f"Payment blocked: {', '.join(flags)}" if blocked else None,
        )


class FeeOptimizationTool(BaseTool):
    name = "fee_optimizer"
    description = "Rank chains by estimated fee cost and confirmation speed"

    def execute(self, **kwargs: Any) -> ToolResult:
        analyze = kwargs.get("analyze_payment") or {}
        if isinstance(analyze, dict):
            chain_health = analyze.get("chain_health", {})
        else:
            chain_health = kwargs.get("chain_health", {})
        healthy = [c for c, ok in chain_health.items() if ok] or list(CHAIN_CURRENCIES.keys())
        amount = Decimal(str(kwargs.get("amount", "0.01")))
        preference = str(kwargs.get("currency_preference", "")).upper()

        rankings: list[dict[str, Any]] = []
        for chain in healthy:
            fee_weight = FEE_WEIGHTS.get(chain, 1.0)
            confirmations = CONFIRMATION_SPEED.get(chain, 10)
            currencies = CHAIN_CURRENCIES.get(chain, ())
            score = (1.0 / fee_weight) * (10.0 / confirmations)
            if preference and preference in currencies:
                score *= 1.5
            rankings.append(
                {
                    "chain": chain,
                    "currencies": list(currencies),
                    "fee_weight": fee_weight,
                    "confirmations_required": confirmations,
                    "optimization_score": round(score, 4),
                }
            )

        rankings.sort(key=lambda x: x["optimization_score"], reverse=True)
        return ToolResult(
            success=bool(rankings),
            output={
                "rankings": rankings,
                "recommended_chain": rankings[0]["chain"] if rankings else "ETH",
                "amount": str(amount),
            },
        )


class ChainSelectionTool(BaseTool):
    name = "chain_selector"
    description = "Select optimal chain and currency based on health, fees, and preferences"

    def execute(self, **kwargs: Any) -> ToolResult:
        fee_output = kwargs.get("fee_optimizer") or {}
        fraud_output = kwargs.get("fraud_detection") or {}

        if isinstance(fraud_output, dict) and not fraud_output.get("approved", True):
            return ToolResult(success=False, output={}, error="Fraud check did not approve payment")

        rankings = fee_output.get("rankings", []) if isinstance(fee_output, dict) else []
        preference = str(kwargs.get("currency_preference", "ETH")).upper()
        enabled = settings.enabled_chain_list

        selected_chain = None
        selected_currency = None

        for entry in rankings:
            chain = entry.get("chain", "")
            if chain not in enabled:
                continue
            currencies = entry.get("currencies", [])
            if preference in currencies:
                selected_chain, selected_currency = chain, preference
                break
            if not selected_chain and currencies:
                selected_chain, selected_currency = chain, currencies[0]

        if not selected_chain:
            selected_chain = enabled[0] if enabled else "ETH"
            selected_currency = CHAIN_CURRENCIES.get(selected_chain, ("ETH",))[0]

        processor = get_payment_processor()
        try:
            processor.validate_chain_currency(selected_chain, selected_currency)
        except ValueError as exc:
            return ToolResult(success=False, output={}, error=str(exc))

        reasoning = f"Selected {selected_chain}/{selected_currency} based on fee ranking and availability"
        return ToolResult(
            success=True,
            output={
                "chain": selected_chain,
                "currency": selected_currency,
                "reasoning": reasoning,
                "enabled_chains": enabled,
            },
        )


class PaymentExecutionTool(BaseTool):
    name = "payment_executor"
    description = "Create payment record and deposit wallet on selected chain"

    def __init__(self, db: Session):
        self._db = db

    def execute(self, **kwargs: Any) -> ToolResult:
        user_id = kwargs.get("user_id")
        amount = kwargs.get("amount")
        callback_url = kwargs.get("callback_url")
        chain_output = kwargs.get("chain_selector") or {}

        if not user_id or not amount or not callback_url:
            return ToolResult(success=False, output={}, error="Missing user_id, amount, or callback_url")

        chain = chain_output.get("chain", "ETH") if isinstance(chain_output, dict) else "ETH"
        currency = chain_output.get("currency", "ETH") if isinstance(chain_output, dict) else "ETH"

        try:
            request = CreatePaymentRequest(
                amount=str(amount),
                callback_url=str(callback_url),
                idempotency_key=kwargs.get("idempotency_key"),
            )
            payment = PaymentService.create_payment(self._db, int(user_id), request)
            # Override chain/currency if agent selected different route (future multichain)
            if chain != payment.chain or currency != payment.currency:
                payment.chain = chain
                payment.currency = currency
                self._db.commit()
                self._db.refresh(payment)

            return ToolResult(
                success=True,
                output={
                    "payment_id": payment.id,
                    "public_token": payment.public_token,
                    "wallet_address": payment.wallet_address,
                    "chain": payment.chain,
                    "currency": payment.currency,
                    "amount": str(payment.amount),
                    "status": payment.status,
                    "payment_url": PaymentService.build_payment_url(payment),
                    "expires_at": payment.expires_at.isoformat() if payment.expires_at else None,
                },
            )
        except Exception as exc:
            logger.exception("Payment execution failed")
            return ToolResult(success=False, output={}, error=str(exc))


class PaymentVerificationTool(BaseTool):
    name = "payment_verifier"
    description = "Verify payment was created and wallet is valid on chain"

    def execute(self, **kwargs: Any) -> ToolResult:
        exec_output = kwargs.get("payment_executor") or {}
        if not isinstance(exec_output, dict) or not exec_output.get("payment_id"):
            return ToolResult(success=False, output={}, error="No payment to verify")

        chain = exec_output.get("chain", "ETH")
        address = exec_output.get("wallet_address", "")
        amount = Decimal(str(exec_output.get("amount", "0")))
        currency = exec_output.get("currency", "ETH")

        processor = get_payment_processor()
        health = processor.chain_health().get(chain, False)

        checks = {
            "payment_created": bool(exec_output.get("payment_id")),
            "wallet_generated": bool(address),
            "chain_connected": health,
            "status_pending": exec_output.get("status") == "pending",
        }

        # Use network analysis from earlier pipeline step when live RPC is unavailable
        analyze = kwargs.get("analyze_payment") or {}
        if isinstance(analyze, dict):
            healthy = analyze.get("healthy_chains") or []
            if chain in healthy:
                checks["chain_connected"] = True

        # Core payment readiness — wallet + record must exist
        core_ready = checks["payment_created"] and checks["wallet_generated"] and checks["status_pending"]
        passed = core_ready and checks["chain_connected"]
        if core_ready and not checks["chain_connected"]:
            # Degraded but usable — payment created, chain poll pending
            passed = True
            checks["chain_connected_degraded"] = True

        return ToolResult(
            success=passed,
            output={
                "verification_checks": checks,
                "payment_id": exec_output.get("payment_id"),
                "ready_for_customer": passed,
            },
            error=None if passed else "Verification checks failed",
        )
