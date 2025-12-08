"""
AdCP MCP Tools for Agentic Advertising Ecosystem

This module provides tools for the Ad Context Protocol (AdCP).

IMPORTANT: When ADCP_GATEWAY_URL is set, MCP is REQUIRED and failures will raise errors.
There is NO silent fallback to mock data in production mode.

Environment Variables:
- ADCP_GATEWAY_URL: URL for AgentCore MCP Gateway (REQUIRED for production)
- ADCP_USE_MCP: Set to "false" ONLY for local development without MCP

Reference: https://docs.adcontextprotocol.org
"""

import json
import logging
import os
from typing import Optional, List, Dict, Any
from strands import tool

logger = logging.getLogger(__name__)

# Lazy initialization - MCP client is created on first use
_mcp_client = None
_mcp_client_initialized = False
_mcp_available = True
_mcp_required = False  # Set to True when ADCP_GATEWAY_URL is configured

# Try to import MCP client module
try:
    from .adcp_mcp_client import create_adcp_mcp_client, MCP_AVAILABLE, SIGV4_AVAILABLE
    _mcp_available = MCP_AVAILABLE
    logger.info(f"AdCP MCP module loaded: MCP_AVAILABLE={MCP_AVAILABLE}, SIGV4_AVAILABLE={SIGV4_AVAILABLE}")
except ImportError as e:
    logger.warning(f"MCP client module not available: {e}")
    _mcp_available = False
    MCP_AVAILABLE = False
    SIGV4_AVAILABLE = False


class MCPConnectionError(Exception):
    """Raised when MCP is required but connection fails"""
    pass


def _get_mcp_client():
    """
    Lazy initialization of MCP client.
    
    When ADCP_GATEWAY_URL is set, MCP is REQUIRED and this will raise
    an error if the client cannot be created.
    """
    global _mcp_client, _mcp_client_initialized, _mcp_required
    
    if _mcp_client_initialized:
        return _mcp_client
    
    _mcp_client_initialized = True
    
    # Log all ADCP-related environment variables for debugging
    logger.info("=" * 60)
    logger.info("🔍 AdCP MCP Client Initialization")
    logger.info(f"   ADCP_GATEWAY_URL: {os.environ.get('ADCP_GATEWAY_URL', 'NOT SET')}")
    logger.info(f"   ADCP_USE_MCP: {os.environ.get('ADCP_USE_MCP', 'NOT SET')}")
    logger.info(f"   AWS_REGION: {os.environ.get('AWS_REGION', 'NOT SET')}")
    logger.info(f"   MCP_AVAILABLE: {_mcp_available}")
    logger.info("=" * 60)
    
    # Check if MCP is explicitly disabled
    use_mcp = os.environ.get("ADCP_USE_MCP", "true").lower() == "true"
    if not use_mcp:
        logger.info("AdCP MCP disabled via ADCP_USE_MCP=false (development mode)")
        _mcp_required = False
        return None
    
    # Get gateway URL - if set, MCP is REQUIRED
    gateway_url = os.environ.get("ADCP_GATEWAY_URL")
    server_path = os.environ.get("ADCP_MCP_SERVER_PATH")
    
    # If gateway URL is configured, MCP is required - no fallback allowed
    if gateway_url:
        _mcp_required = True
        logger.info(f"ADCP_GATEWAY_URL is set to: {gateway_url}")
        logger.info(f"MCP is REQUIRED (no fallback)")
    
    if not _mcp_available:
        if _mcp_required:
            raise MCPConnectionError(
                "MCP dependencies not available but ADCP_GATEWAY_URL is set. "
                "Install MCP dependencies or unset ADCP_GATEWAY_URL."
            )
        logger.warning("MCP dependencies not available. Running in development mode.")
        return None
    
    logger.info(f"Initializing AdCP MCP client: gateway_url={gateway_url}")
    
    try:
        if gateway_url:
            _mcp_client = create_adcp_mcp_client(
                transport="http",
                gateway_url=gateway_url
            )
            if _mcp_client:
                logger.info(f"✅ AdCP MCP client created: {gateway_url}")
            else:
                raise MCPConnectionError(
                    f"Failed to create MCP client for gateway: {gateway_url}. "
                    "Check gateway URL and AWS credentials."
                )
        elif server_path:
            _mcp_client = create_adcp_mcp_client(
                transport="stdio",
                server_path=server_path
            )
            if not _mcp_client:
                logger.warning("Failed to create stdio MCP client")
        else:
            logger.info("No ADCP_GATEWAY_URL set - running in development mode")
            
    except MCPConnectionError:
        raise
    except Exception as e:
        if _mcp_required:
            raise MCPConnectionError(f"MCP client creation failed: {e}")
        logger.error(f"Error creating MCP client: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    return _mcp_client


def _call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Call an MCP tool.
    
    When MCP is required (ADCP_GATEWAY_URL is set), this will raise an error
    if the call fails. There is NO silent fallback.
    
    This function first tries the direct gateway call (proven to work),
    then falls back to MCPClient if direct call is not available.
    """
    gateway_url = os.environ.get("ADCP_GATEWAY_URL")
    region = os.environ.get("AWS_REGION", "us-east-1")
    
    logger.info(f"🔌 _call_mcp_tool: {tool_name}")
    logger.info(f"   Gateway URL: {gateway_url or 'NOT SET'}")
    logger.info(f"   Region: {region}")
    logger.info(f"   Arguments: {json.dumps(arguments)[:200]}...")
    
    # If gateway URL is set, try direct gateway call first (proven to work)
    if gateway_url:
        try:
            from .adcp_mcp_client import call_gateway_tool_sync
            logger.info(f"🔌 Attempting direct gateway call for: {tool_name}")
            result = call_gateway_tool_sync(tool_name, arguments, gateway_url, region)
            if result:
                logger.info(f"✅ Direct gateway call succeeded for {tool_name}")
                result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                logger.info(f"   Result preview: {result_str[:200]}...")
                return result_str
            else:
                logger.warning(f"⚠️ Direct gateway call returned None for {tool_name}")
        except ImportError as e:
            logger.warning(f"Direct gateway call not available: {e}")
            logger.warning("Falling back to MCPClient approach")
        except Exception as e:
            logger.error(f"❌ Direct gateway call failed: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            logger.warning("Falling back to MCPClient approach")
    
    # Fall back to MCPClient approach
    client = _get_mcp_client()
    
    if client is None:
        if _mcp_required:
            raise MCPConnectionError(
                f"MCP client not available for {tool_name} but MCP is required. "
                "Check ADCP_GATEWAY_URL configuration."
            )
        # Only return None (allowing fallback) if MCP is not required
        logger.debug(f"MCP not configured, using development fallback for {tool_name}")
        return None
    
    try:
        # Try to get the prefixed tool name for gateway
        full_tool_name = tool_name
        if gateway_url:
            try:
                from .adcp_mcp_client import get_gateway_tool_name
                full_tool_name = get_gateway_tool_name(tool_name, gateway_url, region)
                logger.info(f"🔌 Calling MCP tool via MCPClient: {full_tool_name} (base: {tool_name})")
            except Exception as e:
                logger.warning(f"Could not get gateway tool name, using base name: {e}")
                full_tool_name = tool_name
        else:
            logger.info(f"🔌 Calling MCP tool: {tool_name}")
        
        with client:
            result = client.call_tool_sync(
                tool_use_id=f"adcp_{tool_name}",
                name=full_tool_name,
                arguments=arguments
            )
            if result and result.get("content"):
                logger.info(f"✅ MCP tool {tool_name} succeeded via MCPClient")
                return result["content"][0].get("text", json.dumps(result))
            else:
                error_msg = f"MCP tool {tool_name} returned empty result"
                if _mcp_required:
                    raise MCPConnectionError(error_msg)
                logger.warning(f"⚠️ {error_msg}")
                return None
                
    except MCPConnectionError:
        raise
    except Exception as e:
        error_msg = f"MCP call failed for {tool_name}: {e}"
        if _mcp_required:
            raise MCPConnectionError(error_msg)
        logger.warning(f"❌ {error_msg}")
        import traceback
        logger.debug(traceback.format_exc())
        return None


def reinitialize_mcp_client():
    """Force re-initialization of the MCP client."""
    global _mcp_client, _mcp_client_initialized, _mcp_required
    _mcp_client = None
    _mcp_client_initialized = False
    _mcp_required = False
    logger.info("MCP client marked for re-initialization")
    return _get_mcp_client()


# ============================================================================
# Tool Implementations
# ============================================================================

@tool
def get_products(
    brief: str,
    channels: Optional[List[str]] = None,
    geo_required: Optional[List[str]] = None,
    brand_safety_tier: str = "tier_1",
    min_budget: Optional[float] = None,
    max_budget: Optional[float] = None
) -> str:
    """
    Discover publisher inventory products matching campaign brief (AdCP Media Buy Protocol).
    
    Args:
        brief: Natural language campaign brief describing target audience and objectives
        channels: Target channels (ctv, online_video, display, audio)
        geo_required: Required geographies (e.g., ["US:CA", "US:OR"])
        brand_safety_tier: Minimum brand safety tier (tier_1, tier_2, tier_3)
        min_budget: Minimum budget per publisher
        max_budget: Maximum budget per publisher
    
    Returns:
        JSON string with matching products from publisher inventory
    """
    logger.info(f"AdCP get_products: brief='{brief[:50]}...', channels={channels}")
    
    result = _call_mcp_tool("get_products", {
        "brief": brief,
        "channels": channels,
        "brand_safety_tier": brand_safety_tier,
        "min_budget": min_budget,
        "max_budget": max_budget
    })
    
    if result:
        return result
    
    # Development-only fallback (only reached if MCP is not required)
    return json.dumps({
        "error": "MCP not configured",
        "message": "Set ADCP_GATEWAY_URL for production use",
        "source": "development_stub",
        "products": [],
        "total_found": 0
    }, indent=2)


@tool
def get_signals(
    brief: str,
    signal_types: Optional[List[str]] = None,
    decisioning_platform: str = "ttd",
    principal_id: Optional[str] = None
) -> str:
    """
    Discover audience and contextual signals for targeting (AdCP Signals Protocol).
    """
    logger.info(f"AdCP get_signals: brief='{brief[:50]}...', types={signal_types}")
    
    result = _call_mcp_tool("get_signals", {
        "brief": brief,
        "signal_types": signal_types,
        "decisioning_platform": decisioning_platform
    })
    
    if result:
        return result
    
    return json.dumps({
        "error": "MCP not configured",
        "message": "Set ADCP_GATEWAY_URL for production use",
        "source": "development_stub",
        "signals": [],
        "total_found": 0
    }, indent=2)


@tool
def activate_signal(
    signal_agent_segment_id: str,
    decisioning_platform: str,
    principal_id: Optional[str] = None,
    account_id: Optional[str] = None
) -> str:
    """
    Activate a signal segment on a decisioning platform (AdCP Signals Protocol).
    """
    logger.info(f"AdCP activate_signal: {signal_agent_segment_id} on {decisioning_platform}")
    
    result = _call_mcp_tool("activate_signal", {
        "signal_agent_segment_id": signal_agent_segment_id,
        "decisioning_platform": decisioning_platform,
        "principal_id": principal_id
    })
    
    if result:
        return result
    
    return json.dumps({
        "error": "MCP not configured",
        "message": "Set ADCP_GATEWAY_URL for production use",
        "source": "development_stub",
        "status": "error"
    }, indent=2)


@tool
def create_media_buy(
    buyer_ref: str,
    packages: List[Dict[str, Any]],
    brand_manifest: Optional[Dict[str, str]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> str:
    """
    Create a media buy with publisher packages (AdCP Media Buy Protocol).
    """
    logger.info(f"AdCP create_media_buy: buyer_ref={buyer_ref}, packages={len(packages)}")
    
    result = _call_mcp_tool("create_media_buy", {
        "buyer_ref": buyer_ref,
        "packages": packages,
        "start_time": start_time,
        "end_time": end_time
    })
    
    if result:
        return result
    
    return json.dumps({
        "error": "MCP not configured",
        "message": "Set ADCP_GATEWAY_URL for production use",
        "source": "development_stub",
        "status": "error"
    }, indent=2)


@tool
def get_media_buy_delivery(
    media_buy_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    Get delivery metrics for a media buy (AdCP Media Buy Protocol).
    """
    logger.info(f"AdCP get_media_buy_delivery: {media_buy_id}")
    
    result = _call_mcp_tool("get_media_buy_delivery", {
        "media_buy_id": media_buy_id,
        "start_date": start_date,
        "end_date": end_date
    })
    
    if result:
        return result
    
    return json.dumps({
        "error": "MCP not configured",
        "message": "Set ADCP_GATEWAY_URL for production use",
        "source": "development_stub",
        "status": "error"
    }, indent=2)


@tool
def verify_brand_safety(
    properties: List[Dict[str, str]],
    brand_safety_tier: str = "tier_1",
    categories_blocked: Optional[List[str]] = None
) -> str:
    """
    Verify brand safety for publisher properties (MCP Verification Service).
    """
    logger.info(f"MCP verify_brand_safety: {len(properties)} properties")
    
    result = _call_mcp_tool("verify_brand_safety", {
        "properties": properties,
        "brand_safety_tier": brand_safety_tier
    })
    
    if result:
        return result
    
    return json.dumps({
        "error": "MCP not configured",
        "message": "Set ADCP_GATEWAY_URL for production use",
        "source": "development_stub",
        "status": "error"
    }, indent=2)


@tool
def resolve_audience_reach(
    audience_segments: List[str],
    channels: Optional[List[str]] = None,
    geo: Optional[List[str]] = None,
    identity_types: Optional[List[str]] = None
) -> str:
    """
    Estimate cross-device reach for audience segments (MCP Identity Service).
    """
    logger.info(f"MCP resolve_audience_reach: segments={audience_segments}")
    
    result = _call_mcp_tool("resolve_audience_reach", {
        "audience_segments": audience_segments,
        "channels": channels,
        "identity_types": identity_types
    })
    
    if result:
        return result
    
    return json.dumps({
        "error": "MCP not configured",
        "message": "Set ADCP_GATEWAY_URL for production use",
        "source": "development_stub",
        "status": "error"
    }, indent=2)


@tool
def configure_brand_lift_study(
    study_name: str,
    study_type: str,
    campaign_id: Optional[str] = None,
    provider: str = "lucid",
    metrics: Optional[List[str]] = None,
    flight_start: Optional[str] = None,
    flight_end: Optional[str] = None,
    sample_size_target: Optional[Dict[str, int]] = None
) -> str:
    """
    Configure a brand lift or attribution measurement study (MCP Measurement Service).
    """
    logger.info(f"MCP configure_brand_lift_study: {study_name}, type={study_type}")
    
    result = _call_mcp_tool("configure_brand_lift_study", {
        "study_name": study_name,
        "study_type": study_type,
        "provider": provider,
        "metrics": metrics,
        "flight_start": flight_start,
        "flight_end": flight_end
    })
    
    if result:
        return result
    
    return json.dumps({
        "error": "MCP not configured",
        "message": "Set ADCP_GATEWAY_URL for production use",
        "source": "development_stub",
        "status": "error"
    }, indent=2)


# ============================================================================
# Exports
# ============================================================================

ADCP_TOOLS = [
    get_products,
    get_signals,
    activate_signal,
    create_media_buy,
    get_media_buy_delivery,
    verify_brand_safety,
    resolve_audience_reach,
    configure_brand_lift_study,
]


def get_adcp_mcp_tools():
    """
    Get AdCP tools for agent integration.
    
    When MCP gateway is available, returns the wrapper tools that call the gateway
    directly with the correct prefixed tool names. This avoids issues with the
    MCPClient managed approach where tool names may not be handled correctly.
    
    When MCP is not available, returns the fallback stub tools.
    """
    gateway_url = os.environ.get("ADCP_GATEWAY_URL")
    
    if gateway_url:
        # When gateway is configured, use our wrapper tools that call the gateway
        # directly with the correct tool names
        logger.info(f"🔧 get_adcp_mcp_tools: Using wrapper tools for gateway: {gateway_url}")
        return ADCP_TOOLS
    else:
        # No gateway configured, return fallback tools
        logger.info("🔧 get_adcp_mcp_tools: No gateway configured, using fallback tools")
        return ADCP_TOOLS


def is_mcp_enabled() -> bool:
    """Check if MCP integration is enabled and available."""
    client = _get_mcp_client()
    return client is not None


def is_mcp_required() -> bool:
    """Check if MCP is required (ADCP_GATEWAY_URL is set)."""
    return _mcp_required
