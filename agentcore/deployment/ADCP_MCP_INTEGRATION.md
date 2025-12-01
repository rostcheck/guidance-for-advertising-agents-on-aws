# AdCP MCP Integration Guide

This guide explains how to set up and use the Ad Context Protocol (AdCP) MCP integration for the Agentic Advertising Ecosystem.

## Overview

The AdCP MCP integration provides two modes of operation:

1. **Fallback Mode** (Default): Uses hardcoded mock data directly in the tools
2. **MCP Mode**: Connects to a real MCP server (local or via AgentCore Gateway)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Handler                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   adcp_tools.py                          │   │
│  │  ┌─────────────┐    ┌─────────────────────────────────┐ │   │
│  │  │ ADCP_TOOLS  │───>│ _call_mcp_tool() or Fallback    │ │   │
│  │  └─────────────┘    └─────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ (if MCP enabled)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Transport Layer                           │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │   stdio (local)     │ OR │   HTTP (AgentCore Gateway)      │ │
│  └─────────────────────┘    └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AdCP MCP Server                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  FastMCP Server (adcp_mcp_server.py)                     │   │
│  │  - get_products (AdCP Media Buy Protocol)                │   │
│  │  - get_signals (AdCP Signals Protocol)                   │   │
│  │  - activate_signal                                       │   │
│  │  - create_media_buy                                      │   │
│  │  - get_media_buy_delivery                                │   │
│  │  - verify_brand_safety (MCP Verification)                │   │
│  │  - resolve_audience_reach (MCP Identity)                 │   │
│  │  - configure_brand_lift_study (MCP Measurement)          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Option 1: Fallback Mode (No Setup Required)

By default, the tools use hardcoded mock data. No additional setup needed:

```python
from shared.adcp_tools import ADCP_TOOLS

# Tools work immediately with mock data
agent = Agent(tools=ADCP_TOOLS)
```

### Option 2: Local MCP Server (Development)

1. Install MCP dependencies:
```bash
pip install mcp strands-agents
```

2. Start the MCP server:
```bash
cd synthetic_data/mcp_mocks
python adcp_mcp_server.py
```

3. Enable MCP in your environment:
```bash
export ADCP_USE_MCP=true
```

4. The tools will now connect to the local MCP server via stdio.

### Option 3: AgentCore Gateway (Production)

1. Deploy the MCP Gateway:
```bash
cd agentcore/deployment
python deploy_adcp_gateway.py \
    --stack-prefix myapp \
    --unique-id abc123 \
    --region us-east-1
```

2. Set environment variables from deployment output:
```bash
export ADCP_USE_MCP=true
export ADCP_GATEWAY_URL=https://your-gateway-url.bedrock-agentcore.us-east-1.amazonaws.com
```

3. The tools will now connect to the AgentCore Gateway via HTTP.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ADCP_USE_MCP` | Enable MCP integration | `false` |
| `ADCP_GATEWAY_URL` | AgentCore Gateway URL | None |
| `ADCP_MCP_SERVER_PATH` | Path to local MCP server | Auto-detected |
| `ADCP_AUTH_TOKEN` | Auth token for gateway | None |

## Testing

### Test Direct Handlers
```bash
cd synthetic_data/mcp_mocks
python test_adcp_server.py
```

### Test MCP Server
```bash
# Terminal 1: Start server
python adcp_mcp_server.py --transport sse --port 8080

# Terminal 2: Test with curl
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "get_products", "arguments": {"brief": "test", "channels": ["ctv"]}}}'
```

### Test Lambda Handler
```bash
cd agentcore/deployment
python deploy_adcp_gateway.py --stack-prefix test --unique-id dev --lambda-only

# Test via AWS CLI
aws lambda invoke \
  --function-name test-adcp-handler-dev \
  --payload '{"tool_name": "get_products", "arguments": {"brief": "test"}}' \
  response.json
```

## Available Tools

### AdCP Media Buy Protocol

| Tool | Description |
|------|-------------|
| `adcp_get_products` | Discover publisher inventory matching campaign brief |
| `adcp_create_media_buy` | Create media buy with publisher packages |
| `adcp_get_media_buy_delivery` | Get delivery metrics for a media buy |

### AdCP Signals Protocol

| Tool | Description |
|------|-------------|
| `adcp_get_signals` | Discover audience and contextual signals |
| `adcp_activate_signal` | Activate segment on DSP platform |

### MCP Services

| Tool | Description |
|------|-------------|
| `mcp_verify_brand_safety` | Verify brand safety for properties |
| `mcp_resolve_audience_reach` | Estimate cross-device reach |
| `mcp_configure_brand_lift_study` | Configure measurement study |

## Integration with Strands Agents

### Using Standard Tools (Fallback)
```python
from strands import Agent
from shared.adcp_tools import ADCP_TOOLS

agent = Agent(
    model=bedrock_model,
    tools=ADCP_TOOLS
)

response = agent("Discover CTV inventory for sports campaign")
```

### Using MCP Client (Managed)
```python
from strands import Agent
from shared.adcp_tools import get_adcp_mcp_tools

# Returns MCP client if enabled, otherwise standard tools
tools = get_adcp_mcp_tools()

agent = Agent(
    model=bedrock_model,
    tools=tools
)
```

### Checking MCP Status
```python
from shared.adcp_tools import is_mcp_enabled

if is_mcp_enabled():
    print("Using MCP server")
else:
    print("Using fallback mode")
```

## Deployment Architecture

### Local Development
```
Agent → adcp_tools.py → stdio → adcp_mcp_server.py (local process)
```

### Production (AgentCore Gateway)
```
Agent → adcp_tools.py → HTTP → AgentCore Gateway → Lambda Handler
```

### Lambda Handler Flow
```
MCP Gateway → Lambda Function → AdCP Protocol Handlers → Response
```

## Troubleshooting

### MCP Not Connecting
1. Check `ADCP_USE_MCP=true` is set
2. Verify MCP dependencies: `pip install mcp strands-agents`
3. Check server is running: `python adcp_mcp_server.py`

### Gateway Errors
1. Verify gateway URL is correct
2. Check authentication token if required
3. Review CloudWatch logs for Lambda errors

### Fallback Mode Active
If you see `"source": "fallback"` in responses, MCP is not connected:
1. Check environment variables
2. Verify MCP server is accessible
3. Check for import errors in logs

## Files Reference

| File | Purpose |
|------|---------|
| `agentcore/deployment/agent/shared/adcp_tools.py` | Main tools with MCP/fallback support |
| `agentcore/deployment/agent/shared/adcp_mcp_client.py` | MCP client wrapper |
| `synthetic_data/mcp_mocks/adcp_mcp_server.py` | FastMCP server implementation |
| `synthetic_data/mcp_mocks/test_adcp_server.py` | Test suite |
| `agentcore/deployment/deploy_adcp_gateway.py` | Gateway deployment script |
