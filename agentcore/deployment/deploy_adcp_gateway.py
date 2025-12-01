#!/usr/bin/env python3
"""
Deploy AdCP MCP Gateway for Agentic Advertising Ecosystem

This script deploys an MCP Gateway via AgentCore CLI with a Lambda target that
implements the Ad Context Protocol (AdCP) for the agentic advertising workflow.

The deployment creates:
1. IAM Role for Lambda execution
2. Lambda function with AdCP protocol handlers
3. MCP Gateway via AgentCore CLI
4. Lambda target attached to the gateway

Usage:
    python deploy_adcp_gateway.py --stack-prefix <prefix> --unique-id <id> --region <region>
    
Example:
    python deploy_adcp_gateway.py --stack-prefix myapp --unique-id abc123 --region us-east-1

After deployment, set the environment variable to enable MCP:
    export ADCP_USE_MCP=true
    export ADCP_GATEWAY_URL=<gateway-url-from-output>
"""

import argparse
import boto3
import json
import logging
import os
import subprocess
import sys
import time
import zipfile
from io import BytesIO

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AdCPGatewayDeployer:
    """Deploy AdCP MCP Gateway with Lambda targets"""
    
    def __init__(self, stack_prefix: str, unique_id: str, region: str = "us-east-1", profile: str = None):
        self.stack_prefix = stack_prefix
        self.unique_id = unique_id
        self.region = region
        self.profile = profile
        
        try:
            # Create boto3 session - use profile if provided, otherwise use default credential chain
            if profile:
                logger.info(f"Using AWS profile: {profile}")
                session = boto3.Session(profile_name=profile, region_name=region)
            else:
                # Check if AWS_PROFILE environment variable is set
                env_profile = os.environ.get('AWS_PROFILE')
                if env_profile:
                    logger.info(f"Using AWS profile from environment: {env_profile}")
                    session = boto3.Session(profile_name=env_profile, region_name=region)
                else:
                    logger.info("No profile specified, using default credential chain")
                    session = boto3.Session(region_name=region)
            
            self.lambda_client = session.client("lambda")
            self.iam_client = session.client("iam")
            self.sts_client = session.client("sts")
            self.account_id = self.sts_client.get_caller_identity()["Account"]
            logger.info(f"Successfully authenticated to AWS account: {self.account_id}")
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {e}")
            logger.error("Please ensure AWS credentials are configured.")
            if profile:
                logger.error(f"Tried to use profile: {profile}")
            else:
                logger.error("No profile was specified. Pass --profile <profile_name> or set AWS_PROFILE environment variable.")
            raise
        
        self.gateway_name = f"{stack_prefix}-adcp-gateway-{unique_id}"
        self.lambda_name = f"{stack_prefix}-adcp-handler-{unique_id}"
        self.role_name = f"{stack_prefix}-adcp-lambda-role-{unique_id}"
        
    def create_lambda_execution_role(self) -> str:
        """Create IAM role for AdCP Lambda functions"""
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }
        
        try:
            response = self.iam_client.create_role(
                RoleName=self.role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="Execution role for AdCP Lambda functions"
            )
            role_arn = response["Role"]["Arn"]
            logger.info(f"Created IAM role: {role_arn}")
            
            # Attach basic Lambda execution policy
            self.iam_client.attach_role_policy(
                RoleName=self.role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
            )
            
            # Wait for role propagation
            logger.info("Waiting for IAM role propagation (10 seconds)...")
            time.sleep(10)  # nosemgrep: arbitrary-sleep - Intentional delay for IAM role propagation
            
            return role_arn
            
        except self.iam_client.exceptions.EntityAlreadyExistsException:
            response = self.iam_client.get_role(RoleName=self.role_name)
            logger.info(f"Using existing IAM role: {response['Role']['Arn']}")
            return response["Role"]["Arn"]
    
    def create_adcp_lambda_code(self) -> bytes:
        """Create Lambda deployment package with AdCP handlers"""
        
        # This is the Lambda handler code that implements AdCP protocol
        lambda_code = '''
"""
AdCP MCP Lambda Handler

This Lambda function implements the Ad Context Protocol (AdCP) for MCP Gateway.
It handles tool calls from the MCP Gateway and returns structured responses.
"""

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ============================================================================
# Mock Data - In production, these would come from databases/APIs
# ============================================================================

PRODUCTS = [
    {"product_id": "prod_espn_ctv_001", "product_name": "Premium Sports CTV - Live Events", "publisher_name": "ESPN", "channel": "ctv", "cpm_usd": 42.50, "min_spend_usd": 10000, "estimated_daily_impressions": 2500000, "brand_safety_tier": "tier_1", "audience_composition": "sports_enthusiasts:0.92,male_25_54:0.68", "format_types": ["video_30s", "video_15s", "interactive"]},
    {"product_id": "prod_fox_ctv_001", "product_name": "Fox Sports CTV - Premium Live", "publisher_name": "Fox Sports", "channel": "ctv", "cpm_usd": 45.00, "min_spend_usd": 15000, "estimated_daily_impressions": 3200000, "brand_safety_tier": "tier_1", "audience_composition": "sports_enthusiasts:0.89,male_25_54:0.71", "format_types": ["video_30s", "video_15s"]},
    {"product_id": "prod_paramount_ctv_001", "product_name": "Paramount+ Sports CTV - NFL AFC", "publisher_name": "Paramount", "channel": "ctv", "cpm_usd": 40.00, "min_spend_usd": 10000, "estimated_daily_impressions": 2000000, "brand_safety_tier": "tier_1", "audience_composition": "sports_enthusiasts:0.87,male_25_54:0.65", "format_types": ["video_30s", "video_15s"]},
    {"product_id": "prod_youtube_olv_001", "product_name": "YouTube Sports Content - Premium", "publisher_name": "Google", "channel": "online_video", "cpm_usd": 22.00, "min_spend_usd": 5000, "estimated_daily_impressions": 8500000, "brand_safety_tier": "tier_1", "audience_composition": "sports_enthusiasts:0.72,male_18_49:0.55", "format_types": ["video_30s", "video_15s", "bumper_6s"]},
    {"product_id": "prod_youtube_env_001", "product_name": "YouTube Environmental Documentaries", "publisher_name": "Google", "channel": "online_video", "cpm_usd": 18.00, "min_spend_usd": 3000, "estimated_daily_impressions": 4200000, "brand_safety_tier": "tier_1", "audience_composition": "eco_conscious:0.85,hhi_75k_plus:0.62", "format_types": ["video_30s", "video_15s"]},
]

SIGNALS = [
    {"signal_id": "sig_lr_001", "signal_name": "Environmentally Conscious Homeowners", "signal_type": "audience", "data_provider": "LiveRamp/Experian", "size_individuals": 42000000, "cpm_usd": 1.75, "accuracy_score": 0.88, "ttd_segment_id": "lr_exp_eco_homeowners", "is_live_ttd": True},
    {"signal_id": "sig_lr_002", "signal_name": "High Income HH $150K+", "signal_type": "audience", "data_provider": "LiveRamp/Experian", "size_individuals": 38000000, "cpm_usd": 1.85, "accuracy_score": 0.92, "ttd_segment_id": "lr_exp_hhi_150k", "is_live_ttd": True},
    {"signal_id": "sig_lr_003", "signal_name": "Sports Enthusiasts - Active Lifestyle", "signal_type": "audience", "data_provider": "LiveRamp/Experian", "size_individuals": 51000000, "cpm_usd": 1.50, "accuracy_score": 0.85, "ttd_segment_id": "lr_exp_sports_active", "is_live_ttd": True},
    {"signal_id": "sig_oracle_001", "signal_name": "Green Technology Intenders", "signal_type": "audience", "data_provider": "Oracle Data Cloud", "size_individuals": 28000000, "cpm_usd": 2.25, "accuracy_score": 0.87, "ttd_segment_id": "oracle_green_tech", "is_live_ttd": True},
    {"signal_id": "sig_p39_001", "signal_name": "Contextual - Environmental Content", "signal_type": "contextual", "data_provider": "Peer39", "size_individuals": 0, "cpm_usd": 0.75, "accuracy_score": 0.94, "ttd_segment_id": "p39_ctx_environmental", "is_live_ttd": True},
]

# In-memory storage for media buys
MEDIA_BUYS = {}


def handler(event, context):
    """Main Lambda handler for AdCP MCP tools"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Extract tool name and arguments from MCP Gateway format
    tool_name = event.get("tool_name") or event.get("name") or event.get("toolName", "")
    arguments = event.get("arguments") or event.get("input") or event.get("toolInput", {})
    
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except:
            arguments = {}
    
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
            return {
                "statusCode": 200,
                "body": json.dumps(result),
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
            }
        except Exception as e:
            logger.error(f"Error handling {tool_name}: {str(e)}")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": str(e)}),
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}]
            }
    
    return {
        "statusCode": 400,
        "body": json.dumps({"error": f"Unknown tool: {tool_name}"}),
        "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"})}]
    }


def handle_get_products(args):
    """AdCP Media Buy Protocol - get_products"""
    channels = args.get("channels", [])
    tier = args.get("brand_safety_tier", "tier_1")
    min_budget = args.get("min_budget")
    
    results = []
    for p in PRODUCTS:
        if channels and p["channel"] not in channels:
            continue
        if tier == "tier_1" and p["brand_safety_tier"] != "tier_1":
            continue
        if min_budget and p["min_spend_usd"] > min_budget:
            continue
        results.append(p)
    
    return {
        "products": results,
        "total_found": len(results),
        "brief_received": args.get("brief", "")[:100],
        "source": "mcp_gateway",
        "message": f"Found {len(results)} products matching criteria"
    }


def handle_get_signals(args):
    """AdCP Signals Protocol - get_signals"""
    signal_types = args.get("signal_types", [])
    platform = args.get("decisioning_platform", "ttd")
    
    results = []
    for s in SIGNALS:
        if signal_types and s["signal_type"] not in signal_types:
            continue
        
        is_live = s.get(f"is_live_{platform}", False)
        segment_id = s.get(f"{platform}_segment_id", "")
        
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
        "source": "mcp_gateway"
    }


def handle_activate_signal(args):
    """AdCP Signals Protocol - activate_signal"""
    signal_id = args.get("signal_agent_segment_id")
    platform = args.get("decisioning_platform", "ttd")
    
    signal = next((s for s in SIGNALS if s["signal_id"] == signal_id), None)
    
    if not signal:
        return {"status": "error", "error_code": "SIGNAL_NOT_FOUND", "message": f"Signal {signal_id} not found"}
    
    segment_id = signal.get(f"{platform}_segment_id", "")
    is_live = signal.get(f"is_live_{platform}", False)
    
    if is_live:
        return {"status": "already_active", "segment_id": segment_id, "signal_name": signal["signal_name"], "message": "Signal already activated"}
    
    return {"status": "activating", "task_id": f"task_{signal_id}_{platform}", "estimated_completion_hours": 4, "message": "Signal activation initiated"}


def handle_create_media_buy(args):
    """AdCP Media Buy Protocol - create_media_buy"""
    import uuid
    buyer_ref = args.get("buyer_ref", "unknown")
    packages = args.get("packages", [])
    
    media_buy_id = f"mb_{buyer_ref[:10].replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    created_packages = []
    total_budget = 0
    
    for i, pkg in enumerate(packages):
        budget = pkg.get("budget", 50000)
        total_budget += budget
        created_packages.append({
            "package_id": f"pkg_{i+1:03d}",
            "product_id": pkg.get("product_id"),
            "budget_usd": budget,
            "status": "active",
            "estimated_impressions": int(budget / 40 * 1000)
        })
    
    MEDIA_BUYS[media_buy_id] = {"media_buy_id": media_buy_id, "packages": created_packages, "total_budget": total_budget}
    
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


def handle_get_media_buy_delivery(args):
    """AdCP Media Buy Protocol - get_media_buy_delivery"""
    media_buy_id = args.get("media_buy_id", "mb_001")
    
    return {
        "media_buy_id": media_buy_id,
        "summary": {
            "impressions_delivered": 1764706,
            "impressions_target": 3529412,
            "pacing_status": "on_track",
            "spend_usd": 75000,
            "budget_usd": 150000,
            "completion_rate": 0.82,
            "viewability_rate": 0.91,
            "ivt_rate": 0.011
        },
        "source": "mcp_gateway",
        "message": "Campaign pacing on track"
    }


def handle_verify_brand_safety(args):
    """MCP Verification Service - verify_brand_safety"""
    properties = args.get("properties", [])
    
    results = []
    for prop in properties:
        url = prop.get("url", "") if isinstance(prop, dict) else str(prop)
        score = 96 if "espn" in url.lower() or "fox" in url.lower() else 89 if "youtube" in url.lower() else 75
        tier = "tier_1" if score >= 90 else "tier_2" if score >= 75 else "tier_3"
        
        results.append({
            "url": url,
            "brand_safety_score": score,
            "brand_safety_tier": tier,
            "risk_flags": [] if score >= 90 else [{"flag": "ugc_content_variability", "severity": "low"}],
            "recommendation": "approved" if score >= 90 else "approved_with_conditions"
        })
    
    return {
        "verification_id": "ver_001",
        "properties": results,
        "summary": {
            "approved": sum(1 for r in results if r["recommendation"] == "approved"),
            "approved_with_conditions": sum(1 for r in results if r["recommendation"] == "approved_with_conditions"),
            "blocked": sum(1 for r in results if r["recommendation"] == "blocked")
        },
        "source": "mcp_gateway"
    }


def handle_resolve_audience_reach(args):
    """MCP Identity Service - resolve_audience_reach"""
    channels = args.get("channels", ["ctv", "mobile", "desktop"])
    
    channel_reach = []
    for ch in channels:
        match_rate = 0.78 if ch == "ctv" else 0.85 if ch == "mobile" else 0.72
        channel_reach.append({
            "channel": ch,
            "reach_households": 700000 if ch == "ctv" else 1200000 if ch == "mobile" else 500000,
            "match_rate": match_rate
        })
    
    return {
        "total_reach_households": 2100000,
        "total_reach_individuals": 4800000,
        "channels": channel_reach,
        "frequency_recommendation": 5,
        "source": "mcp_gateway",
        "message": "Reach estimation complete"
    }


def handle_configure_study(args):
    """MCP Measurement Service - configure_brand_lift_study"""
    study_name = args.get("study_name", "Unnamed Study")
    study_type = args.get("study_type", "brand_lift")
    provider = args.get("provider", "lucid")
    
    cost_map = {"brand_lift": 8000, "foot_traffic": 10000, "sales_lift": 15000, "attribution": 12000}
    
    return {
        "status": "configured",
        "study_id": f"study_{provider[:3]}_{study_type[:4]}_001",
        "study_name": study_name,
        "configuration": {
            "study_type": study_type,
            "provider": provider,
            "methodology": "survey_control_exposed",
            "metrics": args.get("metrics", ["brand_awareness", "ad_recall"]),
            "sample_targets": {"control": 4500, "exposed": 12500}
        },
        "cost_usd": cost_map.get(study_type, 8000),
        "source": "mcp_gateway",
        "message": f"{study_type} study configured successfully"
    }
'''
        
        # Create zip file in memory
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('lambda_function.py', lambda_code)
        
        return zip_buffer.getvalue()
    
    def deploy_adcp_lambda(self) -> str:
        """Deploy Lambda function for AdCP protocol"""
        role_arn = self.create_lambda_execution_role()
        code_zip = self.create_adcp_lambda_code()
        
        try:
            response = self.lambda_client.create_function(
                FunctionName=self.lambda_name,
                Runtime="python3.11",
                Role=role_arn,
                Handler="lambda_function.handler",
                Code={"ZipFile": code_zip},
                Description="AdCP MCP Protocol Handler for Agentic Advertising Ecosystem",
                Timeout=30,
                MemorySize=256,
                Environment={
                    "Variables": {
                        "STACK_PREFIX": self.stack_prefix,
                        "UNIQUE_ID": self.unique_id
                    }
                }
            )
            logger.info(f"Created Lambda function: {response['FunctionArn']}")
            
            # Wait for Lambda to be active
            logger.info("Waiting for Lambda function to be active...")
            waiter = self.lambda_client.get_waiter('function_active')
            waiter.wait(FunctionName=self.lambda_name)
            
            return response["FunctionArn"]
            
        except self.lambda_client.exceptions.ResourceConflictException:
            # Update existing function
            self.lambda_client.update_function_code(
                FunctionName=self.lambda_name,
                ZipFile=code_zip
            )
            response = self.lambda_client.get_function(FunctionName=self.lambda_name)
            logger.info(f"Updated existing Lambda function: {response['Configuration']['FunctionArn']}")
            return response["Configuration"]["FunctionArn"]
    
    def get_existing_gateway(self) -> dict:
        """Check if gateway already exists and return its info"""
        logger.info(f"Checking for existing gateway: {self.gateway_name}")
        
        # Set up environment with AWS_PROFILE if specified
        env = os.environ.copy()
        if self.profile:
            env["AWS_PROFILE"] = self.profile
        
        try:
            # List gateways to find existing one
            cmd = [
                "agentcore", "gateway", "list-mcp-gateways",
                "--region", self.region
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)  # nosemgrep: dangerous-subprocess-use-audit
            
            if result.returncode == 0 and self.gateway_name in result.stdout:
                logger.info(f"Found existing gateway: {self.gateway_name}")
                
                # Try to get gateway details
                get_cmd = [
                    "agentcore", "gateway", "get-mcp-gateway",
                    "--name", self.gateway_name,
                    "--region", self.region
                ]
                
                get_result = subprocess.run(get_cmd, capture_output=True, text=True, timeout=60, env=env)  # nosemgrep: dangerous-subprocess-use-audit
                
                if get_result.returncode == 0:
                    # Parse output to get gateway ARN and URL
                    gateway_info = {}
                    output_lines = get_result.stdout.strip().split('\n')
                    for line in output_lines:
                        line_lower = line.lower()
                        if "arn:" in line_lower or "gatewayarn" in line_lower.replace(" ", "").replace("_", ""):
                            # Extract ARN from line
                            if "arn:aws:" in line:
                                arn_start = line.find("arn:aws:")
                                arn_end = line.find(" ", arn_start) if " " in line[arn_start:] else len(line)
                                gateway_info["gateway_arn"] = line[arn_start:arn_end].strip().rstrip(',').strip('"')
                        if "url" in line_lower or "endpoint" in line_lower:
                            # Extract URL from line
                            if "https://" in line:
                                url_start = line.find("https://")
                                url_end = line.find(" ", url_start) if " " in line[url_start:] else len(line)
                                gateway_info["gateway_url"] = line[url_start:url_end].strip().rstrip(',').strip('"')
                    
                    if gateway_info:
                        return {"status": "exists", "output": get_result.stdout, **gateway_info}
                
                # If we couldn't parse details, still return that it exists
                return {"status": "exists", "output": result.stdout}
            
            return {"status": "not_found"}
            
        except subprocess.TimeoutExpired:
            return {"status": "check_timeout"}
        except FileNotFoundError:
            return {"status": "cli_not_found"}
        except Exception as e:
            logger.warning(f"Error checking for existing gateway: {e}")
            return {"status": "check_error", "message": str(e)}
    
    def create_gateway(self) -> dict:
        """Create MCP Gateway using AgentCore CLI, or return existing one"""
        logger.info(f"Creating MCP Gateway: {self.gateway_name}")
        
        # First check if gateway already exists
        existing = self.get_existing_gateway()
        if existing.get("status") == "exists":
            logger.info(f"Gateway already exists: {self.gateway_name}")
            logger.info("Using existing gateway instead of creating new one")
            return {
                "status": "success",
                "already_existed": True,
                **{k: v for k, v in existing.items() if k != "status"}
            }
        
        cmd = [
            "agentcore", "gateway", "create-mcp-gateway",
            "--name", self.gateway_name,
            "--region", self.region
        ]
        
        # Set up environment with AWS_PROFILE if specified
        # (agentcore CLI doesn't support --profile flag, uses env var instead)
        env = os.environ.copy()
        if self.profile:
            env["AWS_PROFILE"] = self.profile
            logger.info(f"Setting AWS_PROFILE={self.profile} for agentcore CLI")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)  # nosemgrep: dangerous-subprocess-use-audit
            
            if result.returncode != 0:
                # Check if error is because gateway already exists (ConflictException)
                if "ConflictException" in result.stderr or "already exists" in result.stderr.lower():
                    logger.info(f"Gateway already exists (detected from error): {self.gateway_name}")
                    # Try to get existing gateway info
                    existing = self.get_existing_gateway()
                    if existing.get("status") == "exists":
                        return {
                            "status": "success",
                            "already_existed": True,
                            **{k: v for k, v in existing.items() if k != "status"}
                        }
                    # Even if we can't get details, return success since gateway exists
                    return {
                        "status": "success",
                        "already_existed": True,
                        "message": "Gateway already exists"
                    }
                
                logger.error(f"Gateway creation failed: {result.stderr}")
                return {"status": "error", "message": result.stderr}
            
            logger.info("Gateway created successfully")
            logger.info(result.stdout)
            
            # Parse output to get gateway ARN and URL
            output_lines = result.stdout.strip().split('\n')
            gateway_info = {}
            for line in output_lines:
                if "arn:" in line.lower():
                    gateway_info["gateway_arn"] = line.strip()
                if "url" in line.lower() or "endpoint" in line.lower():
                    gateway_info["gateway_url"] = line.strip()
            
            return {"status": "success", "output": result.stdout, **gateway_info}
            
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "message": "Gateway creation timed out"}
        except FileNotFoundError:
            return {"status": "cli_not_found", "message": "AgentCore CLI not found. Install with: pip install bedrock-agentcore-starter-toolkit"}
    
    def add_lambda_target(self, gateway_arn: str, gateway_url: str, role_arn: str, lambda_arn: str) -> dict:
        """Add Lambda target to MCP Gateway"""
        logger.info(f"Adding Lambda target to gateway: {self.lambda_name}")
        
        cmd = [
            "agentcore", "gateway", "create-mcp-gateway-target",
            "--gateway-arn", gateway_arn,
            "--gateway-url", gateway_url,
            "--role-arn", role_arn,
            "--name", f"{self.gateway_name}-lambda-target",
            "--target-type", "lambda",
            "--region", self.region
        ]
        
        # Set up environment with AWS_PROFILE if specified
        env = os.environ.copy()
        if self.profile:
            env["AWS_PROFILE"] = self.profile
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)  # nosemgrep: dangerous-subprocess-use-audit
            
            if result.returncode != 0:
                logger.error(f"Target creation failed: {result.stderr}")
                return {"status": "error", "message": result.stderr}
            
            logger.info("Lambda target added successfully")
            return {"status": "success", "output": result.stdout}
            
        except subprocess.TimeoutExpired:
            return {"status": "timeout"}
        except FileNotFoundError:
            return {"status": "cli_not_found"}
    
    def deploy(self) -> dict:
        """Full deployment: Lambda + Gateway + Target"""
        results = {
            "stack_prefix": self.stack_prefix,
            "unique_id": self.unique_id,
            "region": self.region,
            "gateway_name": self.gateway_name,
            "lambda_name": self.lambda_name
        }
        
        # Step 1: Deploy Lambda
        logger.info("=" * 60)
        logger.info("Step 1: Deploying AdCP Lambda function")
        logger.info("=" * 60)
        try:
            lambda_arn = self.deploy_adcp_lambda()
            results["lambda_arn"] = lambda_arn
            results["lambda_status"] = "success"
        except Exception as e:
            logger.error(f"Lambda deployment failed: {e}")
            results["lambda_status"] = "failed"
            results["lambda_error"] = str(e)
            return results
        
        # Step 2: Create Gateway
        logger.info("=" * 60)
        logger.info("Step 2: Creating MCP Gateway")
        logger.info("=" * 60)
        gateway_result = self.create_gateway()
        results["gateway_result"] = gateway_result
        
        if gateway_result.get("status") == "cli_not_found":
            logger.warning("AgentCore CLI not found. Lambda deployed but gateway requires manual setup.")
            logger.info("")
            logger.info("To complete setup manually:")
            logger.info(f"  1. Install CLI: pip install bedrock-agentcore-starter-toolkit")
            logger.info(f"  2. Create gateway: agentcore gateway create-mcp-gateway --name {self.gateway_name} --region {self.region}")
            logger.info(f"  3. Add Lambda target with the gateway ARN and URL from step 2")
            results["status"] = "partial"
            return results
        
        if gateway_result.get("status") != "success":
            results["status"] = "gateway_failed"
            return results
        
        # Step 3: Add Lambda target (if we have gateway info)
        if gateway_result.get("gateway_arn") and gateway_result.get("gateway_url"):
            logger.info("=" * 60)
            logger.info("Step 3: Adding Lambda target to gateway")
            logger.info("=" * 60)
            
            # Get role ARN
            role_response = self.iam_client.get_role(RoleName=self.role_name)
            role_arn = role_response["Role"]["Arn"]
            
            target_result = self.add_lambda_target(
                gateway_result["gateway_arn"],
                gateway_result["gateway_url"],
                role_arn,
                lambda_arn
            )
            results["target_result"] = target_result
        
        results["status"] = "success"
        
        # Print summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("DEPLOYMENT COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Lambda ARN: {results.get('lambda_arn')}")
        if gateway_result.get("gateway_url"):
            logger.info(f"Gateway URL: {gateway_result['gateway_url']}")
            logger.info("")
            logger.info("To enable MCP integration in your agents:")
            logger.info(f"  export ADCP_USE_MCP=true")
            logger.info(f"  export ADCP_GATEWAY_URL={gateway_result['gateway_url']}")
        
        return results


def main():
    parser = argparse.ArgumentParser(description="Deploy AdCP MCP Gateway for Agentic Advertising")
    parser.add_argument("--stack-prefix", required=True, help="Stack prefix for resource naming")
    parser.add_argument("--unique-id", required=True, help="Unique identifier for this deployment")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument("--lambda-only", action="store_true", help="Deploy only Lambda (skip gateway)")
    
    args = parser.parse_args()
    
    logger.info(f"Starting AdCP Gateway deployment...")
    logger.info(f"  Stack Prefix: {args.stack_prefix}")
    logger.info(f"  Unique ID: {args.unique_id}")
    logger.info(f"  Region: {args.region}")
    logger.info(f"  Profile: {args.profile or 'default'}")
    
    try:
        deployer = AdCPGatewayDeployer(
            stack_prefix=args.stack_prefix,
            unique_id=args.unique_id,
            region=args.region,
            profile=args.profile
        )
    except Exception as e:
        error_result = {
            "status": "error",
            "message": f"Failed to initialize deployer: {str(e)}",
            "hint": "Check AWS credentials and profile configuration"
        }
        print(json.dumps(error_result, indent=2))
        return 1
    
    if args.lambda_only:
        # Just deploy Lambda
        try:
            lambda_arn = deployer.deploy_adcp_lambda()
            print(json.dumps({"status": "success", "lambda_arn": lambda_arn}, indent=2))
            return 0
        except Exception as e:
            print(json.dumps({"status": "error", "message": str(e)}, indent=2))
            return 1
    
    # Full deployment
    try:
        result = deployer.deploy()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") in ["success", "partial"] else 1
    except Exception as e:
        error_result = {
            "status": "error",
            "message": f"Deployment failed: {str(e)}"
        }
        print(json.dumps(error_result, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
