#!/usr/bin/env python3
"""
AdCP MCP Lambda Handler

This Lambda function implements the Ad Context Protocol (AdCP) for MCP Gateway.
It handles tool calls from the MCP Gateway and returns structured responses.

The Lambda reads data from CSV files that are bundled with the deployment package.
These CSV files come from synthetic_data/mcp_mocks/ and contain the actual
advertising ecosystem data (products, signals, campaigns, etc.).

Deployed via: agentcore/deployment/deploy_adcp_gateway.py
"""

import csv
import json
import logging
import os
from io import StringIO
from typing import Any, Dict, List, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ============================================================================
# Data Loading - Load from bundled CSV files
# ============================================================================

# Get the directory where this Lambda is deployed
LAMBDA_DIR = os.path.dirname(os.path.abspath(__file__))

def load_csv_data(filename: str) -> List[Dict[str, Any]]:
    """Load data from a CSV file bundled with the Lambda."""
    filepath = os.path.join(LAMBDA_DIR, "data", filename)
    
    # Try alternate filename if primary not found
    if not os.path.exists(filepath):
        # Try without spaces/parentheses variations
        alt_filename = filename.replace(" (1)", "").replace(" ", "_")
        alt_filepath = os.path.join(LAMBDA_DIR, "data", alt_filename)
        if os.path.exists(alt_filepath):
            filepath = alt_filepath
        else:
            logger.warning(f"CSV file not found: {filepath} or {alt_filepath}, using empty list")
            return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = []
            for row in reader:
                # Convert numeric fields
                processed_row = {}
                for key, value in row.items():
                    if value == '':
                        processed_row[key] = None
                    elif key in ['cpm_usd', 'avg_cpm_usd', 'min_spend_usd', 'accuracy_score', 
                                 'revenue_share_pct', 'coverage_percentage']:
                        try:
                            processed_row[key] = float(value)
                        except (ValueError, TypeError):
                            processed_row[key] = value
                    elif key in ['estimated_daily_impressions', 'estimated_daily_reach', 
                                 'size_individuals', 'size_households']:
                        try:
                            processed_row[key] = int(value)
                        except (ValueError, TypeError):
                            processed_row[key] = value
                    elif key in ['is_live_ttd', 'is_live_dv360', 'is_live_xandr']:
                        processed_row[key] = value.lower() == 'true'
                    else:
                        processed_row[key] = value
                data.append(processed_row)
            logger.info(f"Loaded {len(data)} records from {filename}")
            return data
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return []


# Lazy-load data on first use
_PRODUCTS = None
_SIGNALS = None
_CAMPAIGNS = None
_MEDIA_BUYS = {}  # In-memory storage for created media buys


def get_products() -> List[Dict]:
    """Get products data, loading from CSV on first call."""
    global _PRODUCTS
    if _PRODUCTS is None:
        _PRODUCTS = load_csv_data("products.csv")
    return _PRODUCTS


def get_signals() -> List[Dict]:
    """Get signals data, loading from CSV on first call."""
    global _SIGNALS
    if _SIGNALS is None:
        _SIGNALS = load_csv_data("signals.csv")
    return _SIGNALS


def get_campaigns() -> List[Dict]:
    """Get campaigns data, loading from CSV on first call."""
    global _CAMPAIGNS
    if _CAMPAIGNS is None:
        _CAMPAIGNS = load_csv_data("campaigns.csv")
    return _CAMPAIGNS


# ============================================================================
# Lambda Handler
# ============================================================================

def handler(event, context):
    """Main Lambda handler for AdCP MCP tools."""
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Extract tool name from context (AgentCore Gateway passes it here)
    # See: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html
    raw_tool_name = None
    
    # Primary method: Get from context.client_context.custom (AgentCore Gateway format)
    if context and hasattr(context, 'client_context') and context.client_context:
        custom_context = getattr(context.client_context, 'custom', None)
        if custom_context:
            raw_tool_name = custom_context.get('bedrockAgentCoreToolName')
            logger.info(f"Got tool name from context.client_context.custom: {raw_tool_name}")
    
    # Fallback: Try to get from event (for direct invocation/testing)
    if not raw_tool_name:
        raw_tool_name = (
            event.get("tool_name") or 
            event.get("name") or 
            event.get("toolName") or
            event.get("tool", {}).get("name", "")
        )
        if raw_tool_name:
            logger.info(f"Got tool name from event: {raw_tool_name}")
    
    # MCP Gateway prefixes tool names with target name: "target-name___tool_name"
    # Strip the prefix to get the actual tool name
    if raw_tool_name and "___" in raw_tool_name:
        tool_name = raw_tool_name.split("___")[-1]
        logger.info(f"Stripped tool name prefix: {raw_tool_name} -> {tool_name}")
    else:
        tool_name = raw_tool_name or ""
    
    # For AgentCore Gateway, the event IS the arguments (not wrapped)
    # For direct invocation, arguments might be nested
    if "arguments" in event or "input" in event or "toolInput" in event:
        arguments = (
            event.get("arguments") or 
            event.get("input") or 
            event.get("toolInput") or
            event.get("tool", {}).get("input", {})
        )
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
    else:
        # AgentCore Gateway: event IS the arguments directly
        arguments = event if event else {}
    
    logger.info(f"Tool: {tool_name}, Arguments: {json.dumps(arguments)}")
    
    # Route to appropriate handler
    handlers = {
        "get_products": handle_get_products,
        "get_signals": handle_get_signals,
        "activate_signal": handle_activate_signal,
        "create_media_buy": handle_create_media_buy,
        "get_media_buy_delivery": handle_get_media_buy_delivery,
        "verify_brand_safety": handle_verify_brand_safety,
        "resolve_audience_reach": handle_resolve_audience_reach,
        "configure_brand_lift_study": handle_configure_study,
    }
    
    if tool_name in handlers:
        try:
            result = handlers[tool_name](arguments)
            return format_response(200, result)
        except Exception as e:
            logger.error(f"Error handling {tool_name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return format_response(500, {"error": str(e)})
    
    return format_response(400, {"error": f"Unknown tool: {tool_name}"})


def format_response(status_code: int, result: Dict) -> Dict:
    """Format response for MCP Gateway."""
    body = json.dumps(result)
    return {
        "statusCode": status_code,
        "body": body,
        "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
    }


# ============================================================================
# Tool Handlers
# ============================================================================

def handle_get_products(args: Dict) -> Dict:
    """AdCP Media Buy Protocol - get_products
    
    Discover publisher inventory products matching campaign criteria.
    """
    channels = args.get("channels", [])
    tier = args.get("brand_safety_tier", "tier_1")
    min_budget = args.get("min_budget")
    max_budget = args.get("max_budget")
    brief = args.get("brief", "")
    
    products = get_products()
    results = []
    
    for p in products:
        # Filter by channel
        if channels:
            product_channel = p.get("channel", "")
            if product_channel not in channels:
                continue
        
        # Filter by brand safety tier
        if tier == "tier_1" and p.get("brand_safety_tier") != "tier_1":
            continue
        
        # Filter by budget
        product_min_spend = p.get("min_spend_usd", 0)
        if min_budget and product_min_spend > min_budget:
            continue
        
        # Build result with relevant fields
        results.append({
            "product_id": p.get("product_id"),
            "product_name": p.get("product_name"),
            "publisher_name": p.get("publisher_name"),
            "property_name": p.get("property_name"),
            "channel": p.get("channel"),
            "cpm_usd": p.get("avg_cpm_usd") or p.get("cpm_usd"),
            "min_spend_usd": product_min_spend,
            "estimated_daily_impressions": p.get("estimated_daily_impressions"),
            "estimated_daily_reach": p.get("estimated_daily_reach"),
            "brand_safety_tier": p.get("brand_safety_tier"),
            "audience_composition": p.get("audience_composition"),
            "format_types": p.get("format_types", "").split(",") if p.get("format_types") else [],
            "geo_available": p.get("geo_available", "").split(",") if p.get("geo_available") else [],
        })
    
    return {
        "products": results,
        "total_found": len(results),
        "brief_received": brief[:100] if brief else "",
        "filters_applied": {
            "channels": channels,
            "brand_safety_tier": tier,
            "min_budget": min_budget,
            "max_budget": max_budget
        },
        "source": "mcp_gateway",
        "message": f"Found {len(results)} products matching criteria"
    }


def handle_get_signals(args: Dict) -> Dict:
    """AdCP Signals Protocol - get_signals
    
    Discover audience and contextual signals for targeting.
    """
    signal_types = args.get("signal_types", [])
    platform = args.get("decisioning_platform", "ttd")
    brief = args.get("brief", "")
    
    signals = get_signals()
    results = []
    
    for s in signals:
        # Filter by signal type
        if signal_types and s.get("signal_type") not in signal_types:
            continue
        
        # Check platform availability
        is_live_key = f"is_live_{platform}"
        segment_id_key = f"{platform}_segment_id"
        
        is_live = s.get(is_live_key, False)
        segment_id = s.get(segment_id_key, "")
        
        results.append({
            "signal_id": s.get("signal_id"),
            "signal_name": s.get("signal_name"),
            "signal_type": s.get("signal_type"),
            "signal_agent": s.get("signal_agent"),
            "data_provider": s.get("data_provider"),
            "size_individuals": s.get("size_individuals"),
            "size_households": s.get("size_households"),
            "cpm_usd": s.get("cpm_usd"),
            "accuracy_score": s.get("accuracy_score"),
            "is_live": is_live,
            "segment_id": segment_id,
            "refresh_frequency": s.get("refresh_frequency"),
        })
    
    return {
        "signals": results,
        "total_found": len(results),
        "brief_received": brief[:100] if brief else "",
        "decisioning_platform": platform,
        "source": "mcp_gateway"
    }


def handle_activate_signal(args: Dict) -> Dict:
    """AdCP Signals Protocol - activate_signal
    
    Activate a signal segment on a decisioning platform.
    """
    signal_id = args.get("signal_agent_segment_id")
    platform = args.get("decisioning_platform", "ttd")
    
    signals = get_signals()
    signal = next((s for s in signals if s.get("signal_id") == signal_id), None)
    
    if not signal:
        return {
            "status": "error",
            "error_code": "SIGNAL_NOT_FOUND",
            "message": f"Signal {signal_id} not found"
        }
    
    is_live_key = f"is_live_{platform}"
    segment_id_key = f"{platform}_segment_id"
    
    segment_id = signal.get(segment_id_key, "")
    is_live = signal.get(is_live_key, False)
    
    if is_live:
        return {
            "status": "already_active",
            "segment_id": segment_id,
            "signal_name": signal.get("signal_name"),
            "message": "Signal already activated on this platform"
        }
    
    return {
        "status": "activating",
        "task_id": f"task_{signal_id}_{platform}",
        "estimated_completion_hours": 4,
        "signal_name": signal.get("signal_name"),
        "message": "Signal activation initiated"
    }


def handle_create_media_buy(args: Dict) -> Dict:
    """AdCP Media Buy Protocol - create_media_buy
    
    Create a media buy with publisher packages.
    """
    import uuid
    
    buyer_ref = args.get("buyer_ref", "unknown")
    packages = args.get("packages", [])
    start_time = args.get("start_time")
    end_time = args.get("end_time")
    
    media_buy_id = f"mb_{buyer_ref[:10].replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    created_packages = []
    total_budget = 0
    
    products = get_products()
    product_map = {p.get("product_id"): p for p in products}
    
    for i, pkg in enumerate(packages):
        budget = pkg.get("budget", 50000)
        total_budget += budget
        
        product_id = pkg.get("product_id")
        product = product_map.get(product_id, {})
        cpm = product.get("avg_cpm_usd") or product.get("cpm_usd") or 40
        
        estimated_impressions = int(budget / cpm * 1000) if cpm > 0 else 0
        
        created_packages.append({
            "package_id": f"pkg_{i+1:03d}",
            "product_id": product_id,
            "product_name": product.get("product_name", "Unknown"),
            "publisher_name": product.get("publisher_name", "Unknown"),
            "budget_usd": budget,
            "status": "active",
            "estimated_impressions": estimated_impressions,
            "targeting": pkg.get("targeting", {}),
            "format_ids": pkg.get("format_ids", ["video_30s", "video_15s"])
        })
    
    # Store media buy for later retrieval
    _MEDIA_BUYS[media_buy_id] = {
        "media_buy_id": media_buy_id,
        "buyer_ref": buyer_ref,
        "packages": created_packages,
        "total_budget_usd": total_budget,
        "start_time": start_time or "2025-02-01T00:00:00Z",
        "end_time": end_time or "2025-03-15T23:59:59Z",
        "status": "active"
    }
    
    return {
        "status": "completed",
        "media_buy_id": media_buy_id,
        "buyer_ref": buyer_ref,
        "creative_deadline": "2025-01-25T23:59:59Z",
        "packages": created_packages,
        "total_budget_usd": total_budget,
        "source": "mcp_gateway",
        "message": f"Media buy created with {len(created_packages)} packages"
    }


def handle_get_media_buy_delivery(args: Dict) -> Dict:
    """AdCP Media Buy Protocol - get_media_buy_delivery
    
    Get delivery metrics for a media buy.
    """
    media_buy_id = args.get("media_buy_id", "mb_001")
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    
    # Check if we have this media buy stored
    media_buy = _MEDIA_BUYS.get(media_buy_id)
    
    # Generate realistic delivery metrics
    total_budget = media_buy.get("total_budget_usd", 150000) if media_buy else 150000
    spend = total_budget * 0.5  # 50% spent
    impressions_target = int(total_budget / 42.5 * 1000)  # Based on avg CPM
    impressions_delivered = int(impressions_target * 0.5)
    
    return {
        "media_buy_id": media_buy_id,
        "reporting_period": {
            "start": start_date or "2025-02-01",
            "end": end_date or "2025-02-15"
        },
        "summary": {
            "impressions_delivered": impressions_delivered,
            "impressions_target": impressions_target,
            "pacing_status": "on_track",
            "spend_usd": spend,
            "budget_usd": total_budget,
            "budget_utilized_pct": 50.0
        },
        "packages": [{
            "package_id": "pkg_001",
            "impressions_delivered": impressions_delivered,
            "reach_households": int(impressions_delivered / 2.94),
            "frequency": 2.94,
            "completion_rate": 0.82,
            "viewability_rate": 0.91,
            "ivt_rate": 0.011,
            "brand_safety_incidents": 0
        }],
        "projection": {
            "expected_final_impressions": impressions_target,
            "expected_final_reach": int(impressions_target / 2.94),
            "confidence": "high"
        },
        "source": "mcp_gateway",
        "message": "Campaign pacing on track. No delivery concerns."
    }


def handle_verify_brand_safety(args: Dict) -> Dict:
    """MCP Verification Service - verify_brand_safety
    
    Verify brand safety for publisher properties.
    """
    properties = args.get("properties", [])
    tier_required = args.get("brand_safety_tier", "tier_1")
    
    products = get_products()
    product_urls = {p.get("property_url", "").lower(): p for p in products}
    
    results = []
    for prop in properties:
        url = prop.get("url", "") if isinstance(prop, dict) else str(prop)
        url_lower = url.lower()
        
        # Check if URL matches a known product
        matched_product = None
        for product_url, product in product_urls.items():
            if product_url and product_url in url_lower:
                matched_product = product
                break
        
        if matched_product:
            tier = matched_product.get("brand_safety_tier", "tier_2")
            score = 96 if tier == "tier_1" else 85 if tier == "tier_2" else 70
        elif "espn" in url_lower or "fox" in url_lower or "nbc" in url_lower:
            score = 96
            tier = "tier_1"
        elif "youtube" in url_lower or "google" in url_lower:
            score = 89
            tier = "tier_1"
        elif "twitch" in url_lower:
            score = 85
            tier = "tier_2"
        else:
            score = 75
            tier = "tier_2"
        
        risk_flags = []
        if "youtube" in url_lower or "twitch" in url_lower:
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
        },
        "source": "mcp_gateway"
    }


def handle_resolve_audience_reach(args: Dict) -> Dict:
    """MCP Identity Service - resolve_audience_reach
    
    Estimate cross-device reach for audience segments.
    """
    audience_segments = args.get("audience_segments", [])
    channels = args.get("channels", ["ctv", "mobile", "desktop"])
    identity_types = args.get("identity_types", ["uid2", "rampid"])
    
    # Calculate reach based on signals data
    signals = get_signals()
    total_individuals = 0
    total_households = 0
    
    for seg_id in audience_segments:
        signal = next((s for s in signals if s.get("signal_id") == seg_id), None)
        if signal:
            total_individuals += signal.get("size_individuals", 0) or 0
            total_households += signal.get("size_households", 0) or 0
    
    # If no specific segments, use average
    if total_individuals == 0:
        total_individuals = 4800000
        total_households = 2100000
    
    channel_reach = []
    for ch in channels:
        if ch == "ctv":
            reach = int(total_households * 0.33)
            match_rate = 0.78
        elif ch == "mobile":
            reach = int(total_households * 0.57)
            match_rate = 0.85
        else:  # desktop
            reach = int(total_households * 0.24)
            match_rate = 0.72
        
        channel_reach.append({
            "channel": ch,
            "reach_households": reach,
            "match_rate": match_rate
        })
    
    return {
        "total_reach_households": total_households,
        "total_reach_individuals": total_individuals,
        "channels": channel_reach,
        "identity_types_used": identity_types,
        "cross_device_overlap": 0.15,
        "frequency_recommendation": 5,
        "confidence_interval": "±8%",
        "segments_analyzed": audience_segments,
        "source": "mcp_gateway",
        "message": "Reach estimation complete. Match rates strong across all channels."
    }


def handle_configure_study(args: Dict) -> Dict:
    """MCP Measurement Service - configure_brand_lift_study
    
    Configure a brand lift or attribution measurement study.
    """
    study_name = args.get("study_name", "Unnamed Study")
    study_type = args.get("study_type", "brand_lift")
    provider = args.get("provider", "lucid")
    metrics = args.get("metrics", ["brand_awareness", "ad_recall", "purchase_intent"])
    flight_start = args.get("flight_start")
    flight_end = args.get("flight_end")
    
    cost_map = {
        "brand_lift": 8000,
        "foot_traffic": 10000,
        "sales_lift": 15000,
        "attribution": 12000
    }
    
    methodology_map = {
        "brand_lift": "survey_control_exposed",
        "foot_traffic": "location_attribution",
        "sales_lift": "purchase_data_matching",
        "attribution": "multi_touch_attribution"
    }
    
    return {
        "status": "configured",
        "study_id": f"study_{provider[:3]}_{study_type[:4]}_{hash(study_name) % 1000:03d}",
        "study_name": study_name,
        "configuration": {
            "study_type": study_type,
            "provider": provider,
            "methodology": methodology_map.get(study_type, "survey_control_exposed"),
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
        "source": "mcp_gateway",
        "message": f"{study_type} study configured successfully. First interim report available Feb 15."
    }
