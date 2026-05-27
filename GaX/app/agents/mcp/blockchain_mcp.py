"""Gaxtron MCP tool server — Model Context Protocol for blockchain tools."""

from __future__ import annotations

from typing import Any

# MCP tool manifest for external agent connections (Gemini Enterprise / ADK)
GAXTRON_MCP_MANIFEST = {
    "name": "gaxtron-blockchain-mcp",
    "version": "1.0.0",
    "description": "MCP server exposing Gaxtron blockchain payment routing tools",
    "tools": [
        {
            "name": "chain_health_check",
            "description": "Check RPC connectivity for enabled blockchain networks",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "fraud_detection",
            "description": "Screen payment for suspicious activity",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "amount": {"type": "string"},
                    "callback_url": {"type": "string"},
                    "user_id": {"type": "integer"},
                },
                "required": ["amount", "callback_url"],
            },
        },
        {
            "name": "fee_optimizer",
            "description": "Rank chains by fee cost and confirmation speed",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "amount": {"type": "string"},
                    "currency_preference": {"type": "string"},
                },
            },
        },
        {
            "name": "chain_selector",
            "description": "Select optimal blockchain and currency",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "payment_executor",
            "description": "Create payment and generate deposit wallet",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "amount": {"type": "string"},
                    "callback_url": {"type": "string"},
                    "user_id": {"type": "integer"},
                },
                "required": ["amount", "callback_url", "user_id"],
            },
        },
        {
            "name": "payment_verifier",
            "description": "Verify payment creation and chain readiness",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ],
}


def get_mcp_manifest() -> dict[str, Any]:
    return GAXTRON_MCP_MANIFEST
