"""Google Cloud Marketplace listing metadata for Gaxtron agent."""

MARKETPLACE_LISTING = {
    "product_name": "Gaxtron Autonomous Payment Router",
    "track": "Track 3 — Refactor for Google Cloud Marketplace & Gemini Enterprise",
    "category": "Fintech / Blockchain Infrastructure",
    "deployment_targets": ["Google Cloud Run", "GKE", "Gemini Enterprise"],
    "agent_type": "event_driven_orchestrator",
    "mcp_compatible": True,
    "gemini_enterprise_ready": True,
    "features": [
        "Autonomous multi-chain payment routing",
        "Fraud detection and risk scoring",
        "Fee optimization across ETH/TRON/BTC/SOL",
        "HMAC webhook delivery",
        "Structured Cloud Logging compatible output",
    ],
    "api_endpoints": [
        "POST /agents/payment/route",
        "GET /agents/mcp/manifest",
        "GET /agents/gcp/readiness",
    ],
}

READINESS_CHECKLIST = {
    "structured_logging": True,
    "health_probes": True,
    "secret_manager_compatible": True,
    "cloud_sql_postgres": True,
    "redis_memorystore": True,
    "vercel_or_cloud_run": True,
    "mcp_tool_manifest": True,
    "idempotent_payments": True,
}
