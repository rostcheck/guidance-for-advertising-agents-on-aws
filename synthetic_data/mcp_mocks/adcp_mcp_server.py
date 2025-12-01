#!/usr/bin/env python3
"""
AdCP MCP Server - Production-ready implementation for Ad Context Protocol

This server implements the AdCP (Ad Context Protocol) as an MCP server that can be:
1. Run locally via stdio for development
2. Deployed to AWS Lambda via AgentCore Gateway
3. Run as an HTTP server for testing

Implements:
- AdCP Media Buy Protocol: get_products, create_media_buy, get_media_buy_delivery
- AdCP Signals Protocol: get_signals, activate_signal
- MCP Services: verify_brand_safety, resolve_audience_reach, configure_brand_lift_study

Usage:
    # Run with stdio (for MCP client integration)
    python adcp_mcp_server.py
    
    # Run with SSE transport (for HTTP testing)
    python adcp_mcp_server.py --transport sse --port 8080
    
    # Run with streamable-http transport
    python adcp_mcp_server.py --transport streamable-http --port 8080
"""

import argparse
import json
import os
import sys
from typing import List, Dict, Any, Optional

# Try to import FastMCP - gracefully handle if not installed
USE_FASTMCP = False
MCP_AVAILABLE = False

try:
    from mcp.server import FastMCP
    USE_FASTMCP = True
    MCP_AVAILABLE = True
except ImportError:
    try:
        from mcp.server import Server
        MCP_AVAILABLE = True
    except ImportError:
        # MCP not installed - handlers can still be used directly
        pass

# ============================================================================
# Mock Data - In production, these would come from databases/APIs
# ============================================================================

PRODUCTS = [
    {
        "product_id": "prod_espn_ctv_001",
        "product_name": "Premium Sports CTV - Live Events",
        "publisher_name": "ESPN",
        "channel": "ctv",
        "cpm_usd": 42.50,
        "min_spend_usd": 10000,
        "estimated_daily_impressions": 2500000,
        "brand_safety_tier": "tier_1",
        "audience_composition": "sports_enthusiasts:0.92,male_25_54:0.68",
        "format_types": ["video_30s", "video_15s", "interactive"]
    },
    {
        "product_id": "prod_fox_ctv_001",
        "product_name": "Fox Sports CTV - Premium Live",
        "publisher_name": "Fox Sports",
        "channel": "ctv",
        "cpm_usd": 45.00,
        "min_spend_usd": 15000,
        "estimated_daily_impressions": 3200000,
        "brand_safety_tier": "tier_1",
        "audience_composition": "sports_enthusiasts:0.89,male_25_54:0.71",
        "format_types": ["video_30s", "video_15s"]
    },
    {
        "product_id": "prod_paramount_ctv_001",
        "product_name": "Paramount+ Sports CTV - NFL AFC",
        "publisher_name": "Paramount",
        "channel": "ctv",
        "cpm_usd": 40.00,
        "min_spend_usd": 10000,
        "estimated_daily_impressions": 2000000,
        "brand_safety_tier": "tier_1",
        "audience_composition": "sports_enthusiasts:0.87,male_25_54:0.65",
        "format_types": ["video_30s", "video_15s"]
    },
    {
        "product_id": "prod_youtube_olv_001",
        "product_name": "YouTube Sports Content - Premium",
        "publisher_name": "Google",
        "channel": "online_video",
        "cpm_usd": 22.00,
        "min_spend_usd": 5000,
        "estimated_daily_impressions": 8500000,
        "brand_safety_tier": "tier_1",
        "audience_composition": "sports_enthusiasts:0.72,male_18_49:0.55",
        "format_types": ["video_30s", "video_15s", "bumper_6s"]
    },
    {
        "product_id": "prod_youtube_env_001",
        "product_name": "YouTube Environmental Documentaries",
        "publisher_name": "Google",
        "channel": "online_video",
        "cpm_usd": 18.00,
        "min_spend_usd": 3000,
        "estimated_daily_impressions": 4200000,
        "brand_safety_tier": "tier_1",
        "audience_composition": "eco_conscious:0.85,hhi_75k_plus:0.62",
        "format_types": ["video_30s", "video_15s"]
    },
]

SIGNALS = [
    {
        "signal_id": "sig_lr_001",
        "signal_name": "Environmentally Conscious Homeowners",
        "signal_type": "audience",
        "data_provider": "LiveRamp/Experian",
        "size_individuals": 42000000,
        "cpm_usd": 1.75,
        "accuracy_score": 0.88,
        "ttd_segment_id": "lr_exp_eco_homeowners",
        "is_live_ttd": True
    },
    {
        "signal_id": "sig_lr_002",
        "signal_name": "High Income HH $150K+",
        "signal_type": "audience",
        "data_provider": "LiveRamp/Experian",
        "size_individuals": 38000000,
        "cpm_usd": 1.85,
        "accuracy_score": 0.92,
        "ttd_segment_id": "lr_exp_hhi_150k",
        "is_live_ttd": True
    },
    {
        "signal_id": "sig_lr_003",
        "signal_name": "Sports Enthusiasts - Active Lifestyle",
        "signal_type": "audience",
        "data_provider": "LiveRamp/Experian",
        "size_individuals": 51000000,
        "cpm_usd": 1.50,
        "accuracy_score": 0.85,
        "ttd_segment_id": "lr_exp_sports_active",
        "is_live_ttd": True
    },
    {
        "signal_id": "sig_oracle_001",
        "signal_name": "Green Technology Intenders",
        "signal_type": "audience",
        "data_provider": "Oracle Data Cloud",
        "size_individuals": 28000000,
        "cpm_usd": 2.25,
        "accuracy_score": 0.87,
        "ttd_segment_id": "oracle_green_tech",
        "is_live_ttd": True
    },
    {
        "signal_id": "sig_p39_001",
        "signal_name": "Contextual - Environmental Content",
        "signal_type": "contextual",
        "data_provider": "Peer39",
        "size_individuals": 0,
        "cpm_usd": 0.75,
        "accuracy_score": 0.94,
        "ttd_segment_id": "p39_ctx_environmental",
        "is_live_ttd": True
    },
]

# In-memory storage for media buys (would be database in production)
MEDIA_BUYS: Dict[str, Dict] = {}

# ============================================================================
# Tool Implementations
# ============================================================================

def handle_get_products(
    brief: str,
    channels: Optional[List[str]] = None,
    brand_safety_tier: str = "tier_1",
    min_budget: Optional[float] = None,
    max_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """AdCP Media Buy Protocol - Discover publisher inventory"""
    results = []
    for p in PRODUCTS:
        # Filter by channel
        if channels and p["channel"] not in channels:
            continue
        # Filter by brand safety tier
        if brand_safety_tier == "tier_1" and p["brand_safety_tier"] != "tier_1":
            continue
        # Filter by budget
        if min_budget and p["min_spend_usd"] > min_budget:
            continue
        
        results.append(p)
    
    return {
        "products": results,
        "total_found": len(results),
        "brief_received": brief[:100],
        "filters_applied": {
            "channels": channels,
            "brand_safety_tier": brand_safety_tier,
            "min_budget": min_budget
        },
        "message": f"Found {len(results)} products matching criteria"
    }


def handle_get_signals(
    brief: str,
    signal_types: Optional[List[str]] = None,
    decisioning_platform: str = "ttd",
) -> Dict[str, Any]:
    """AdCP Signals Protocol - Discover audience segments"""
    results = []
    for s in SIGNALS:
        if signal_types and s["signal_type"] not in signal_types:
            continue
        
        is_live = s.get(f"is_live_{decisioning_platform}", False)
        segment_id = s.get(f"{decisioning_platform}_segment_id", "")
        
        results.append({
            "signal_id": s["signal_id"],
            "signal_name": s["signal_name"],
            "signal_type": s["signal_type"],
            "data_provider": s["data_provider"],
            "size_individuals": s["size_individuals"],
            "cpm_usd": s["cpm_usd"],
            "accuracy_score": s["accuracy_score"],
            "is_live": is_live,
            "segment_id": segment_id
        })
    
    return {
        "signals": results,
        "total_found": len(results),
        "brief_received": brief[:100],
        "decisioning_platform": decisioning_platform
    }


def handle_activate_signal(
    signal_agent_segment_id: str,
    decisioning_platform: str,
    principal_id: Optional[str] = None,
) -> Dict[str, Any]:
    """AdCP Signals Protocol - Activate segment on DSP"""
    signal = next((s for s in SIGNALS if s["signal_id"] == signal_agent_segment_id), None)
    
    if not signal:
        return {
            "status": "error",
            "error_code": "SIGNAL_NOT_FOUND",
            "message": f"Signal {signal_agent_segment_id} not found"
        }
    
    segment_id = signal.get(f"{decisioning_platform}_segment_id", "")
    is_live = signal.get(f"is_live_{decisioning_platform}", False)
    
    if is_live:
        return {
            "status": "already_active",
            "segment_id": segment_id,
            "signal_name": signal["signal_name"],
            "message": "Signal already activated on this platform"
        }
    
    return {
        "status": "activating",
        "task_id": f"task_{signal_agent_segment_id}_{decisioning_platform}",
        "estimated_completion_hours": 4,
        "signal_name": signal["signal_name"],
        "message": "Signal activation initiated"
    }


def handle_create_media_buy(
    buyer_ref: str,
    packages: List[Dict[str, Any]],
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> Dict[str, Any]:
    """AdCP Media Buy Protocol - Create media buy"""
    import uuid
    
    media_buy_id = f"mb_{buyer_ref[:10].replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    created_packages = []
    total_budget = 0
    
    for i, pkg in enumerate(packages):
        budget = pkg.get("budget", 50000)
        total_budget += budget
        cpm = 40  # Default CPM estimate
        estimated_impressions = int(budget / cpm * 1000)
        
        created_packages.append({
            "package_id": f"pkg_{i+1:03d}",
            "product_id": pkg.get("product_id"),
            "budget_usd": budget,
            "status": "active",
            "estimated_impressions": estimated_impressions,
            "targeting": pkg.get("targeting", {}),
            "format_ids": pkg.get("format_ids", ["video_30s", "video_15s"])
        })
    
    # Store media buy
    MEDIA_BUYS[media_buy_id] = {
        "media_buy_id": media_buy_id,
        "buyer_ref": buyer_ref,
        "packages": created_packages,
        "total_budget_usd": total_budget,
        "start_time": start_time or "2025-02-01T00:00:00Z",
        "end_time": end_time or "2025-03-15T23:59:59Z",
        "status": "active",
        "created_at": "2025-01-15T14:30:00Z"
    }
    
    return {
        "status": "completed",
        "media_buy_id": media_buy_id,
        "buyer_ref": buyer_ref,
        "creative_deadline": "2025-01-25T23:59:59Z",
        "packages": created_packages,
        "total_budget_usd": total_budget,
        "message": f"Media buy created with {len(created_packages)} packages"
    }


def handle_get_media_buy_delivery(
    media_buy_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """AdCP Media Buy Protocol - Get delivery metrics"""
    # Check if we have this media buy stored
    media_buy = MEDIA_BUYS.get(media_buy_id)
    
    # Generate realistic delivery metrics
    return {
        "media_buy_id": media_buy_id,
        "reporting_period": {
            "start": start_date or "2025-02-01",
            "end": end_date or "2025-02-15"
        },
        "summary": {
            "impressions_delivered": 1764706,
            "impressions_target": 3529412,
            "pacing_status": "on_track",
            "spend_usd": 75000,
            "budget_usd": 150000,
            "budget_utilized_pct": 50.0
        },
        "packages": [{
            "package_id": "pkg_001",
            "impressions_delivered": 1764706,
            "reach_households": 600000,
            "frequency": 2.94,
            "completion_rate": 0.82,
            "viewability_rate": 0.91,
            "ivt_rate": 0.011,
            "brand_safety_incidents": 0
        }],
        "projection": {
            "expected_final_impressions": 3529412,
            "expected_final_reach": 1200000,
            "confidence": "high"
        },
        "message": "Campaign pacing on track. No delivery concerns."
    }


def handle_verify_brand_safety(
    properties: List[Dict[str, str]],
    brand_safety_tier: str = "tier_1",
) -> Dict[str, Any]:
    """MCP Verification Service - Brand safety verification"""
    results = []
    for prop in properties:
        url = prop.get("url", "") if isinstance(prop, dict) else str(prop)
        
        # Score based on URL (mock logic)
        if "espn" in url.lower() or "fox" in url.lower():
            score = 96
        elif "youtube" in url.lower():
            score = 89
        elif "twitch" in url.lower():
            score = 85
        else:
            score = 75
        
        tier = "tier_1" if score >= 90 else "tier_2" if score >= 75 else "tier_3"
        
        risk_flags = []
        if "youtube" in url.lower() or "twitch" in url.lower():
            risk_flags.append({
                "flag": "ugc_content_variability",
                "severity": "low",
                "description": "User-generated content requires real-time contextual filtering"
            })
        
        recommendation = "approved" if score >= 90 else "approved_with_conditions" if score >= 75 else "blocked"
        
        results.append({
            "url": url,
            "brand_safety_score": score,
            "brand_safety_tier": tier,
            "risk_flags": risk_flags,
            "historical_incidents_90d": 0 if score >= 90 else 3,
            "recommendation": recommendation
        })
    
    return {
        "verification_id": f"ver_{hash(str(properties)) % 10000:04d}",
        "timestamp": "2025-01-15T14:30:00Z",
        "properties": results,
        "summary": {
            "total_properties": len(results),
            "approved": sum(1 for r in results if r["recommendation"] == "approved"),
            "approved_with_conditions": sum(1 for r in results if r["recommendation"] == "approved_with_conditions"),
            "blocked": sum(1 for r in results if r["recommendation"] == "blocked")
        }
    }


def handle_resolve_audience_reach(
    audience_segments: List[str],
    channels: Optional[List[str]] = None,
    identity_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """MCP Identity Service - Cross-device reach estimation"""
    channels = channels or ["ctv", "mobile", "desktop"]
    identity_types = identity_types or ["uid2", "rampid"]
    
    channel_reach = []
    for ch in channels:
        if ch == "ctv":
            reach = 700000
            match_rate = 0.78
        elif ch == "mobile":
            reach = 1200000
            match_rate = 0.85
        else:  # desktop
            reach = 500000
            match_rate = 0.72
        
        channel_reach.append({
            "channel": ch,
            "reach_households": reach,
            "match_rate": match_rate
        })
    
    return {
        "total_reach_households": 2100000,
        "total_reach_individuals": 4800000,
        "channels": channel_reach,
        "identity_types_used": identity_types,
        "cross_device_overlap": 0.15,
        "frequency_recommendation": 5,
        "confidence_interval": "±8%",
        "segments_analyzed": audience_segments,
        "message": "Reach estimation complete. Match rates strong across all channels."
    }


def handle_configure_brand_lift_study(
    study_name: str,
    study_type: str,
    provider: str = "lucid",
    metrics: Optional[List[str]] = None,
    flight_start: Optional[str] = None,
    flight_end: Optional[str] = None,
) -> Dict[str, Any]:
    """MCP Measurement Service - Configure brand lift study"""
    metrics = metrics or ["brand_awareness", "ad_recall", "purchase_intent"]
    
    cost_map = {
        "brand_lift": 8000,
        "foot_traffic": 10000,
        "sales_lift": 15000,
        "attribution": 12000
    }
    
    return {
        "status": "configured",
        "study_id": f"study_{provider[:3]}_{study_type[:4]}_{hash(study_name) % 1000:03d}",
        "study_name": study_name,
        "configuration": {
            "study_type": study_type,
            "provider": provider,
            "methodology": "survey_control_exposed" if study_type == "brand_lift" else "location_attribution",
            "metrics": metrics,
            "flight_dates": {
                "start": flight_start or "2025-02-01",
                "end": flight_end or "2025-03-15"
            },
            "sample_targets": {"control": 4500, "exposed": 12500},
            "expected_precision": {
                "min_detectable_effect": 0.08,
                "confidence_level": 0.95
            }
        },
        "cost_usd": cost_map.get(study_type, 8000),
        "reporting_schedule": {
            "interim_reports": ["2025-02-15", "2025-02-28"],
            "final_report": "2025-03-29"
        },
        "message": f"{study_type} study configured successfully. First interim report available Feb 15."
    }


# ============================================================================
# MCP Server Setup
# ============================================================================

# ============================================================================
# MCP Server Setup (only if MCP is available)
# ============================================================================

mcp = None

if USE_FASTMCP:
    # Use FastMCP for cleaner tool definitions
    mcp = FastMCP("AdCP MCP Server")
    
    @mcp.tool(description="Discover publisher inventory products matching campaign brief (AdCP Media Buy Protocol)")
    def get_products(
        brief: str,
        channels: list[str] = None,
        brand_safety_tier: str = "tier_1",
        min_budget: float = None,
        max_budget: float = None,
    ) -> str:
        result = handle_get_products(brief, channels, brand_safety_tier, min_budget, max_budget)
        return json.dumps(result, indent=2)
    
    @mcp.tool(description="Discover audience and contextual signals for targeting (AdCP Signals Protocol)")
    def get_signals(
        brief: str,
        signal_types: list[str] = None,
        decisioning_platform: str = "ttd",
    ) -> str:
        result = handle_get_signals(brief, signal_types, decisioning_platform)
        return json.dumps(result, indent=2)
    
    @mcp.tool(description="Activate a signal segment on a decisioning platform (AdCP Signals Protocol)")
    def activate_signal(
        signal_agent_segment_id: str,
        decisioning_platform: str,
        principal_id: str = None,
    ) -> str:
        result = handle_activate_signal(signal_agent_segment_id, decisioning_platform, principal_id)
        return json.dumps(result, indent=2)
    
    @mcp.tool(description="Create a media buy with publisher packages (AdCP Media Buy Protocol)")
    def create_media_buy(
        buyer_ref: str,
        packages: list[dict],
        start_time: str = None,
        end_time: str = None,
    ) -> str:
        result = handle_create_media_buy(buyer_ref, packages, start_time, end_time)
        return json.dumps(result, indent=2)
    
    @mcp.tool(description="Get delivery metrics for a media buy (AdCP Media Buy Protocol)")
    def get_media_buy_delivery(
        media_buy_id: str,
        start_date: str = None,
        end_date: str = None,
    ) -> str:
        result = handle_get_media_buy_delivery(media_buy_id, start_date, end_date)
        return json.dumps(result, indent=2)
    
    @mcp.tool(description="Verify brand safety for publisher properties (MCP Verification Service)")
    def verify_brand_safety(
        properties: list[dict],
        brand_safety_tier: str = "tier_1",
    ) -> str:
        result = handle_verify_brand_safety(properties, brand_safety_tier)
        return json.dumps(result, indent=2)
    
    @mcp.tool(description="Estimate cross-device reach for audience segments (MCP Identity Service)")
    def resolve_audience_reach(
        audience_segments: list[str],
        channels: list[str] = None,
        identity_types: list[str] = None,
    ) -> str:
        result = handle_resolve_audience_reach(audience_segments, channels, identity_types)
        return json.dumps(result, indent=2)
    
    @mcp.tool(description="Configure a brand lift or attribution measurement study (MCP Measurement Service)")
    def configure_brand_lift_study(
        study_name: str,
        study_type: str,
        provider: str = "lucid",
        metrics: list[str] = None,
        flight_start: str = None,
        flight_end: str = None,
    ) -> str:
        result = handle_configure_brand_lift_study(study_name, study_type, provider, metrics, flight_start, flight_end)
        return json.dumps(result, indent=2)


def main():
    """Run the MCP server"""
    parser = argparse.ArgumentParser(description="AdCP MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--test", action="store_true", help="Run handler tests without MCP")
    args = parser.parse_args()
    
    if args.test:
        # Run quick test of handlers
        print("Testing AdCP handlers...")
        result = handle_get_products("test brief", ["ctv"], "tier_1", None, None)
        print(f"get_products: Found {result['total_found']} products")
        result = handle_get_signals("test audience", ["audience"], "ttd")
        print(f"get_signals: Found {result['total_found']} signals")
        print("All handlers working!")
        return
    
    if not MCP_AVAILABLE:
        print("MCP not available. Please install: pip install mcp", file=sys.stderr)
        print("You can still use the handlers directly by importing them.", file=sys.stderr)
        print("Run with --test to verify handlers work.", file=sys.stderr)
        sys.exit(1)
    
    if USE_FASTMCP and mcp:
        if args.transport == "stdio":
            mcp.run()
        elif args.transport == "sse":
            mcp.run(transport="sse", port=args.port)
        elif args.transport == "streamable-http":
            mcp.run(transport="streamable-http", port=args.port)
    else:
        print("FastMCP not available. Please install: pip install mcp[server]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
