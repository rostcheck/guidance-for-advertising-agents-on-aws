#!/usr/bin/env python3
"""
Runtime Registry for A2A Bearer Token Management

This module manages a centralized registry of AgentCore runtimes with their A2A bearer tokens.
All runtimes can access this registry to get bearer tokens for calling other A2A agents.

Registry Format:
{
    "runtimes": {
        "arn:aws:bedrock-agentcore:region:account:runtime/id": {
            "name": "agent-name",
            "bearer_token": "token",
            "pool_id": "pool-id",
            "client_id": "client-id",
            "discovery_url": "url",
            "protocol": "A2A",
            "updated_at": "2024-01-15T10:30:00Z"
        }
    }
}
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional


class RuntimeRegistry:
    """Manages the runtime registry file for A2A bearer tokens"""

    def __init__(self, stack_prefix: str, unique_id: str, project_root: str = None):
        self.stack_prefix = stack_prefix
        self.unique_id = unique_id
        self.project_root = project_root or os.getcwd()
        self.registry_file = os.path.join(
            self.project_root,
            f".agentcore-runtime-registry-{stack_prefix}-{unique_id}.json",
        )

    def load_registry(self) -> Dict[str, Any]:
        """Load the runtime registry from file"""
        if os.path.exists(self.registry_file):
            with open(self.registry_file, "r") as f:
                return json.load(f)
        return {"runtimes": {}}

    def save_registry(self, registry: Dict[str, Any]):
        """Save the runtime registry to file"""
        with open(self.registry_file, "w") as f:
            json.dump(registry, f, indent=2)

    def register_runtime(
        self,
        runtime_arn: str,
        agent_name: str,
        bearer_token: str = None,
        pool_id: str = None,
        client_id: str = None,
        discovery_url: str = None,
        protocol: str = None,
    ):
        """
        Register a runtime with optional A2A configuration

        Args:
            runtime_arn: The runtime ARN
            agent_name: The agent name
            bearer_token: Bearer token for A2A (optional)
            pool_id: Cognito pool ID (optional)
            client_id: Cognito client ID (optional)
            discovery_url: OIDC discovery URL (optional)
            protocol: Protocol type (optional, defaults to "A2A" if bearer_token provided)
        """
        registry = self.load_registry()

        runtime_info = {
            "name": agent_name,
            "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # Add A2A configuration if provided
        if bearer_token:
            runtime_info.update(
                {
                    "bearer_token": bearer_token,
                    "pool_id": pool_id or "",
                    "client_id": client_id or "",
                    "discovery_url": discovery_url or "",
                    "protocol": protocol or "A2A",
                }
            )

        registry["runtimes"][runtime_arn] = runtime_info
        self.save_registry(registry)

        return runtime_info

    def get_runtime_info(self, runtime_arn: str) -> Optional[Dict[str, Any]]:
        """Get runtime information by ARN"""
        registry = self.load_registry()
        return registry["runtimes"].get(runtime_arn)

    def get_bearer_token(self, runtime_arn: str) -> Optional[str]:
        """Get bearer token for a specific runtime"""
        runtime_info = self.get_runtime_info(runtime_arn)
        if runtime_info:
            return runtime_info.get("bearer_token")
        return None

    def get_all_runtimes(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered runtimes"""
        registry = self.load_registry()
        return registry.get("runtimes", {})

    def build_runtimes_env_value(self) -> str:
        """
        Build the RUNTIMES environment variable value with bearer tokens

        Format: arn1|bearer_token1,arn2|bearer_token2,...
        For non-A2A runtimes: arn|
        """
        registry = self.load_registry()
        runtimes = registry.get("runtimes", {})

        runtime_entries = []
        for arn, info in runtimes.items():
            bearer_token = info.get("bearer_token", "")
            runtime_entries.append(f"{arn}|{bearer_token}")

        return ",".join(runtime_entries)

    def remove_runtime(self, runtime_arn: str):
        """Remove a runtime from the registry"""
        registry = self.load_registry()
        if runtime_arn in registry["runtimes"]:
            del registry["runtimes"][runtime_arn]
            self.save_registry(registry)


def main():
    """CLI interface for runtime registry management"""
    import argparse

    parser = argparse.ArgumentParser(description="Manage AgentCore Runtime Registry")
    parser.add_argument("--stack-prefix", required=True, help="Stack prefix")
    parser.add_argument("--unique-id", required=True, help="Unique ID")
    parser.add_argument(
        "--action",
        required=True,
        choices=["register", "get", "list", "build-env", "remove"],
    )
    parser.add_argument("--runtime-arn", help="Runtime ARN")
    parser.add_argument("--agent-name", help="Agent name")
    parser.add_argument("--bearer-token", help="Bearer token")
    parser.add_argument("--pool-id", help="Cognito pool ID")
    parser.add_argument("--client-id", help="Cognito client ID")
    parser.add_argument("--discovery-url", help="OIDC discovery URL")
    parser.add_argument("--protocol", help="Protocol type")

    args = parser.parse_args()

    registry = RuntimeRegistry(args.stack_prefix, args.unique_id)

    if args.action == "register":
        if not args.runtime_arn or not args.agent_name:
            print("Error: --runtime-arn and --agent-name required for register")
            return 1

        info = registry.register_runtime(
            args.runtime_arn,
            args.agent_name,
            args.bearer_token,
            args.pool_id,
            args.client_id,
            args.discovery_url,
            args.protocol,
        )
        print(json.dumps(info, indent=2))

    elif args.action == "get":
        if not args.runtime_arn:
            print("Error: --runtime-arn required for get")
            return 1

        info = registry.get_runtime_info(args.runtime_arn)
        if info:
            print(json.dumps(info, indent=2))
        else:
            print(f"Runtime not found: {args.runtime_arn}")
            return 1

    elif args.action == "list":
        runtimes = registry.get_all_runtimes()
        print(json.dumps(runtimes, indent=2))

    elif args.action == "build-env":
        env_value = registry.build_runtimes_env_value()
        print(env_value)

    elif args.action == "remove":
        if not args.runtime_arn:
            print("Error: --runtime-arn required for remove")
            return 1

        registry.remove_runtime(args.runtime_arn)
        print(f"Removed runtime: {args.runtime_arn}")

    return 0


if __name__ == "__main__":
    exit(main())
