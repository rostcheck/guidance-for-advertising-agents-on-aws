#!/bin/bash

# Script to update AgentCore agent endpoint URLs for production deployment
# Usage: ./update_production_endpoint.sh <agent_name> <production_endpoint_url>

set -e

AGENT_NAME="${1}"
PRODUCTION_URL="${2}"
AGENTCORE_CONFIG="bedrock-adtech-demo/src/assets/agentcore-agents.json"

if [ -z "$AGENT_NAME" ] || [ -z "$PRODUCTION_URL" ]; then
    echo "Usage: $0 <agent_name> <production_endpoint_url>"
    echo "Example: $0 weather-agent https://agentcore-weather-agent.us-east-1.elb.amazonaws.com"
    exit 1
fi

echo "🔄 Updating endpoint URL for $AGENT_NAME to $PRODUCTION_URL"

# Check if the config file exists
if [ ! -f "$AGENTCORE_CONFIG" ]; then
    echo "❌ AgentCore config file not found: $AGENTCORE_CONFIG"
    exit 1
fi

# Create a backup
cp "$AGENTCORE_CONFIG" "${AGENTCORE_CONFIG}.backup"

# Update the endpoint URL using jq
if command -v jq >/dev/null 2>&1; then
    # Use jq if available
    jq --arg name "$AGENT_NAME" --arg url "$PRODUCTION_URL" \
       '(.agentcore_agents[] | select(.name == $name) | .endpointUrl) = $url' \
       "$AGENTCORE_CONFIG" > "${AGENTCORE_CONFIG}.tmp" && \
       mv "${AGENTCORE_CONFIG}.tmp" "$AGENTCORE_CONFIG"
    
    echo "✅ Updated endpoint URL for $AGENT_NAME"
    echo "📄 Backup saved as ${AGENTCORE_CONFIG}.backup"
else
    # Fallback using sed (less reliable but works without jq)
    echo "⚠️  jq not found, using sed (less reliable)"
    sed -i.backup "s|\"endpointUrl\": \"[^\"]*\"|\"endpointUrl\": \"$PRODUCTION_URL\"|g" "$AGENTCORE_CONFIG"
    echo "✅ Updated endpoint URL (please verify manually)"
fi

echo ""
echo "🔍 Current configuration:"
if command -v jq >/dev/null 2>&1; then
    jq --arg name "$AGENT_NAME" '.agentcore_agents[] | select(.name == $name) | {name, endpointUrl, runtimeArn}' "$AGENTCORE_CONFIG"
else
    grep -A 10 -B 2 "\"name\": \"$AGENT_NAME\"" "$AGENTCORE_CONFIG"
fi

echo ""
echo "📝 Next steps:"
echo "1. Test the endpoint: curl $PRODUCTION_URL/health"
echo "2. Restart your Angular application to pick up the new configuration"
echo "3. Test the agent in the UI"