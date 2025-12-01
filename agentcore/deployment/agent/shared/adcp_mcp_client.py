"""
AdCP MCP Client Integration for Agentic Advertising Ecosystem

This module provides MCP client integration for connecting to AdCP MCP servers.
It supports both local MCP servers (via stdio) and remote MCP Gateways (via HTTP).

Usage:
    # For local development with stdio server
    mcp_client = create_adcp_mcp_client(transport="stdio")
    
    # For AgentCore Gateway
    mcp_client = create_adcp_mcp_client(
        transport="http",
        gateway_url="https://your-gateway-url.bedrock-agentcore.us-east-1.amazonaws.com"
    )
"""

import os
import logging
from typing import Optional, List, Callable, Any

logger = logging.getLogger(__name__)

# Check if MCP dependencies are available
try:
    from mcp import stdio_client, StdioServerParameters
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("MCP dependencies not available. Install with: pip install mcp strands-agents")


def create_adcp_mcp_client(
    transport: str = "stdio",
    gateway_url: Optional[str] = None,
    server_path: Optional[str] = None,
    auth_token: Optional[str] = None,
    tool_prefix: str = "adcp",
) -> Optional[Any]:
    """
    Create an MCP client for AdCP protocol tools.
    
    Args:
        transport: Transport type - "stdio" for local server, "http" for gateway
        gateway_url: URL for HTTP gateway (required if transport="http")
        server_path: Path to local MCP server script (for stdio transport)
        auth_token: Authentication token for gateway
        tool_prefix: Prefix for tool names to avoid conflicts
    
    Returns:
        MCPClient instance or None if MCP not available
    """
    if not MCP_AVAILABLE:
        logger.error("MCP dependencies not installed")
        return None
    
    if transport == "stdio":
        return _create_stdio_client(server_path, tool_prefix)
    elif transport == "http":
        return _create_http_client(gateway_url, auth_token, tool_prefix)
    else:
        raise ValueError(f"Unknown transport: {transport}")


def _create_stdio_client(server_path: Optional[str], prefix: str) -> Any:
    """Create stdio-based MCP client for local development"""
    if server_path is None:
        # Default to the mock server in synthetic_data
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        server_path = os.path.join(base_dir, "synthetic_data", "mcp_mocks", "adcp_mcp_server.py")
    
    if not os.path.exists(server_path):
        logger.error(f"MCP server not found at: {server_path}")
        return None
    
    logger.info(f"Creating stdio MCP client with server: {server_path}")
    
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="python",
                args=[server_path]
            )
        ),
        prefix=prefix
    )


def _create_http_client(gateway_url: Optional[str], auth_token: Optional[str], prefix: str) -> Any:
    """Create HTTP-based MCP client for AgentCore Gateway"""
    if not gateway_url:
        gateway_url = os.environ.get("ADCP_GATEWAY_URL")
    
    if not gateway_url:
        logger.error("Gateway URL required for HTTP transport. Set ADCP_GATEWAY_URL env var.")
        return None
    
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    elif os.environ.get("ADCP_AUTH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['ADCP_AUTH_TOKEN']}"
    
    logger.info(f"Creating HTTP MCP client with gateway: {gateway_url}")
    
    return MCPClient(
        lambda: streamablehttp_client(
            url=gateway_url,
            headers=headers if headers else None
        ),
        prefix=prefix
    )


def get_adcp_tools_from_mcp(mcp_client: Any) -> List[Callable]:
    """
    Get tools from MCP client for use with Strands agent.
    
    Args:
        mcp_client: MCPClient instance
    
    Returns:
        List of tool functions
    """
    if mcp_client is None:
        logger.warning("MCP client is None, returning empty tools list")
        return []
    
    try:
        # Use the managed approach - MCPClient implements ToolProvider
        # The agent will handle lifecycle automatically
        return [mcp_client]
    except Exception as e:
        logger.error(f"Failed to get tools from MCP client: {e}")
        return []


class AdCPMCPToolProvider:
    """
    Tool provider that wraps AdCP MCP client for use with Strands agents.
    
    This class provides a clean interface for integrating AdCP MCP tools
    into the agent handler, supporting both local and gateway deployments.
    """
    
    def __init__(
        self,
        transport: str = "stdio",
        gateway_url: Optional[str] = None,
        server_path: Optional[str] = None,
        auth_token: Optional[str] = None,
    ):
        self.transport = transport
        self.gateway_url = gateway_url
        self.server_path = server_path
        self.auth_token = auth_token
        self._client = None
        self._tools = None
    
    @property
    def client(self) -> Optional[Any]:
        """Lazy initialization of MCP client"""
        if self._client is None:
            self._client = create_adcp_mcp_client(
                transport=self.transport,
                gateway_url=self.gateway_url,
                server_path=self.server_path,
                auth_token=self.auth_token,
            )
        return self._client
    
    def get_tools(self) -> List[Any]:
        """Get tools for agent integration"""
        if self.client is None:
            return []
        return [self.client]
    
    def is_available(self) -> bool:
        """Check if MCP integration is available"""
        return MCP_AVAILABLE and self.client is not None


# Singleton instance for easy access
_default_provider: Optional[AdCPMCPToolProvider] = None


def get_default_adcp_provider() -> AdCPMCPToolProvider:
    """Get or create the default AdCP MCP tool provider"""
    global _default_provider
    if _default_provider is None:
        # Determine transport based on environment
        gateway_url = os.environ.get("ADCP_GATEWAY_URL")
        if gateway_url:
            _default_provider = AdCPMCPToolProvider(
                transport="http",
                gateway_url=gateway_url
            )
        else:
            _default_provider = AdCPMCPToolProvider(transport="stdio")
    return _default_provider
