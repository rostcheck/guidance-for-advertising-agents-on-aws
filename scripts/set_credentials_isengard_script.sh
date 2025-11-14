#!/bin/bash

# AWS Credentials Setup Script using Isengard
# Usage: ./set_credentials_isengard_script.sh [OPTIONS] [POSITIONAL_ARGS]

# Default values
DEFAULT_ACCOUNT="123456789012"
DEFAULT_ROLE="Admin"
DEFAULT_PROFILE="rtbag"
DEFAULT_REGION="us-west-2"

# Initialize variables with defaults
ACCOUNT_NUMBER="$DEFAULT_ACCOUNT"
IAM_ROLE_NAME="$DEFAULT_ROLE"
AWS_PROFILE_NAME="$DEFAULT_PROFILE"
AWS_REGION="$DEFAULT_REGION"

# Function to parse command line arguments
parse_args() {
    local positional_count=0
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --account|--account-number)
                ACCOUNT_NUMBER="$2"
                shift 2
                ;;
            --role|--iam-role)
                IAM_ROLE_NAME="$2"
                shift 2
                ;;
            --profile)
                AWS_PROFILE_NAME="$2"
                shift 2
                ;;
            --region)
                AWS_REGION="$2"
                shift 2
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            -*)
                echo "❌ Error: Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                # Handle positional arguments for backward compatibility
                case $positional_count in
                    0) ACCOUNT_NUMBER="$1" ;;
                    1) IAM_ROLE_NAME="$1" ;;
                    2) AWS_PROFILE_NAME="$1" ;;
                    3) AWS_REGION="$1" ;;
                    *)
                        echo "❌ Error: Too many positional arguments"
                        show_usage
                        exit 1
                        ;;
                esac
                positional_count=$((positional_count + 1))
                shift
                ;;
        esac
    done
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS] [POSITIONAL_ARGS]"
    echo ""
    echo "Named Options:"
    echo "  --account, --account-number ACCOUNT   AWS account number (default: $DEFAULT_ACCOUNT)"
    echo "  --role, --iam-role ROLE              IAM role name to assume (default: $DEFAULT_ROLE)"
    echo "  --profile PROFILE                    AWS CLI profile name (default: $DEFAULT_PROFILE)"
    echo "  --region REGION                      AWS region (default: $DEFAULT_REGION)"
    echo "  -h, --help                           Show this help message"
    echo ""
    echo "Positional Arguments (for backward compatibility):"
    echo "  $0 [ACCOUNT_NUMBER] [IAM_ROLE_NAME] [PROFILE_NAME] [REGION]"
    echo ""
    echo "Examples:"
    echo "  # Named parameters (recommended)"
    echo "  $0 --account 123456789012 --role Admin --profile prod --region us-east-1"
    echo "  $0 --account 123456789012 --profile production"
    echo "  $0 --region us-east-1"
    echo ""
    echo "  # Positional parameters (legacy)"
    echo "  $0                                           # Use all defaults"
    echo "  $0 123456789012                              # Custom account only"
    echo "  $0 123456789012 Admin              # Custom account and role"
    echo "  $0 123456789012 Admin prod         # Custom account, role, and profile"
    echo "  $0 123456789012 Admin prod us-east-1  # Fully custom"
    echo ""
    echo "Mixed usage:"
    echo "  $0 123456789012 --profile production --region us-east-1"
    echo ""
}

# Parse command line arguments
parse_args "$@"

# Validate account number format (12 digits)
if [[ ! "$ACCOUNT_NUMBER" =~ ^[0-9]{12}$ ]]; then
    echo "❌ Error: Account number must be exactly 12 digits"
    echo "   Provided: '$ACCOUNT_NUMBER'"
    show_usage
    exit 1
fi

echo "🔐 Setting up AWS credentials using Isengard"
echo "   Account: $ACCOUNT_NUMBER"
echo "   Role: $IAM_ROLE_NAME"
echo "   Profile: $AWS_PROFILE_NAME"
echo "   Region: $AWS_REGION"
echo ""

# Initialize midway session
echo "🔑 Initializing midway session..."
mwinit

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to initialize midway session"
    echo "   Make sure you have access to the AWS account and mwinit is properly configured"
    exit 1
fi

# Get credentials from Isengard
echo "📡 Fetching credentials from Isengard..."
echo "🔍 Debug: Making request to Isengard for account $ACCOUNT_NUMBER with role $IAM_ROLE_NAME"

# First get the raw response to debug
raw_response=$(curl -b ~/.midway/cookie -c ~/.midway/cookie -L -X POST \
    --header "X-Amz-Target: IsengardService.GetAssumeRoleCredentials" \
    --header "Content-Encoding: amz-1.0" \
    --header "Content-Type: application/json; charset=UTF-8" \
    -d "{\"AWSAccountID\": \"$ACCOUNT_NUMBER\", \"IAMRoleName\":\"$IAM_ROLE_NAME\"}" \
    https://isengard-service.amazon.com 2>/dev/null)

curl_exit_code=$?
echo "🔍 Debug: Curl exit code: $curl_exit_code"

if [ $curl_exit_code -ne 0 ]; then
    echo "❌ Error: Failed to connect to Isengard service (curl exit code: $curl_exit_code)"
    echo "   Please check your network connection and midway session"
    exit 1
fi

if [ -z "$raw_response" ]; then
    echo "❌ Error: Empty response from Isengard"
    echo "   Please check your midway session and account access"
    exit 1
fi

echo "🔍 Debug: Raw response length: ${#raw_response} characters"
echo "🔍 Debug: Raw response (first 200 chars): ${raw_response:0:200}"

# Check if response contains error
if echo "$raw_response" | grep -q "error\|Error\|ERROR"; then
    echo "❌ Error: Isengard returned an error response:"
    echo "$raw_response"
    exit 1
fi

# Try to parse the credentials
credentials=$(echo "$raw_response" | jq -r '.AssumeRoleResult | fromjson | .credentials' 2>/dev/null)
jq_exit_code=$?

if [ $jq_exit_code -ne 0 ] || [ -z "$credentials" ] || [ "$credentials" == "null" ]; then
    echo "❌ Error: Failed to parse credentials from Isengard response"
    echo "   jq exit code: $jq_exit_code"
    echo "   Raw response: $raw_response"
    echo ""
    echo "   Please check:"
    echo "   - Your midway session is valid (try running 'mwinit' again)"
    echo "   - You have access to account $ACCOUNT_NUMBER"
    echo "   - The role '$IAM_ROLE_NAME' exists and you can assume it"
    echo "   - Your Isengard permissions are correct"
    exit 1
fi

echo "🔍 Debug: Successfully parsed credentials from response"

# Extract and set environment variables
echo "🔧 Setting AWS environment variables..."
export AWS_SECRET_ACCESS_KEY="$(echo "$credentials" | jq -r '.secretAccessKey')"
export AWS_SESSION_TOKEN="$(echo "$credentials" | jq -r '.sessionToken')"
export AWS_ACCESS_KEY_ID="$(echo "$credentials" | jq -r '.accessKeyId')"
export AWS_PROFILE="$AWS_PROFILE_NAME"

# Configure AWS CLI profile with debugging
echo "🔧 Configuring AWS CLI profile '$AWS_PROFILE_NAME'..."
echo "🔍 Debug: Setting profile configuration..."

# Set each configuration value and check for errors
echo "   Setting access key..."
aws configure set profile.$AWS_PROFILE_NAME.aws_access_key_id "$AWS_ACCESS_KEY_ID"
if [ $? -ne 0 ]; then
    echo "❌ Warning: Failed to set access key for profile"
fi

echo "   Setting secret key..."
aws configure set profile.$AWS_PROFILE_NAME.aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"
if [ $? -ne 0 ]; then
    echo "❌ Warning: Failed to set secret key for profile"
fi

echo "   Setting session token..."
aws configure set profile.$AWS_PROFILE_NAME.aws_session_token "$AWS_SESSION_TOKEN"
if [ $? -ne 0 ]; then
    echo "❌ Warning: Failed to set session token for profile"
fi

echo "   Setting region..."
aws configure set profile.$AWS_PROFILE_NAME.region "$AWS_REGION"
if [ $? -ne 0 ]; then
    echo "❌ Warning: Failed to set region for profile"
fi

# Verify profile was configured
echo "🔍 Debug: Verifying profile configuration..."
echo "   Profile configuration for '$AWS_PROFILE_NAME':"
aws configure list --profile "$AWS_PROFILE_NAME" 2>/dev/null || echo "   ❌ Failed to read profile configuration"

# Check if ~/.aws directory exists
if [ ! -d ~/.aws ]; then
    echo "❌ Warning: ~/.aws directory does not exist"
    echo "   Creating ~/.aws directory..."
    mkdir -p ~/.aws
    chmod 700 ~/.aws
fi

# Show the actual files
echo "🔍 Debug: AWS configuration files:"
if [ -f ~/.aws/credentials ]; then
    echo "   ~/.aws/credentials exists ($(wc -l < ~/.aws/credentials) lines)"
    echo "   Profile '$AWS_PROFILE_NAME' in credentials:"
    grep -A 4 "\\[$AWS_PROFILE_NAME\\]" ~/.aws/credentials 2>/dev/null || echo "   Profile not found in credentials file"
else
    echo "   ~/.aws/credentials does not exist"
fi

if [ -f ~/.aws/config ]; then
    echo "   ~/.aws/config exists ($(wc -l < ~/.aws/config) lines)"
    echo "   Profile '$AWS_PROFILE_NAME' in config:"
    grep -A 4 "\\[profile $AWS_PROFILE_NAME\\]" ~/.aws/config 2>/dev/null || echo "   Profile not found in config file"
else
    echo "   ~/.aws/config does not exist"
fi

# Validate that we got valid credentials
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ "$AWS_ACCESS_KEY_ID" == "null" ]; then
    echo "❌ Error: Failed to extract valid credentials"
    echo "   The response from Isengard may not contain valid credential data"
    echo "   Credentials object: $credentials"
    exit 1
fi

# Test the credentials
echo "🧪 Testing AWS credentials..."

# First validate the credential values we extracted
echo "🔍 Debug: Validating extracted credentials..."
echo "   Access Key ID length: ${#AWS_ACCESS_KEY_ID}"
echo "   Secret Key length: ${#AWS_SECRET_ACCESS_KEY}"
echo "   Session Token length: ${#AWS_SESSION_TOKEN}"

if [[ ${#AWS_ACCESS_KEY_ID} -lt 16 ]]; then
    echo "❌ Warning: Access Key ID seems too short (${#AWS_ACCESS_KEY_ID} chars)"
fi

if [[ ${#AWS_SECRET_ACCESS_KEY} -lt 30 ]]; then
    echo "❌ Warning: Secret Access Key seems too short (${#AWS_SECRET_ACCESS_KEY} chars)"
fi

if [[ ${#AWS_SESSION_TOKEN} -lt 100 ]]; then
    echo "❌ Warning: Session Token seems too short (${#AWS_SESSION_TOKEN} chars)"
fi

# Test with detailed error output
echo "🔍 Debug: Testing AWS CLI with profile '$AWS_PROFILE_NAME'..."
aws_test_output=$(aws sts get-caller-identity --profile $AWS_PROFILE_NAME 2>&1)
aws_test_exit_code=$?

echo "🔍 Debug: AWS CLI exit code: $aws_test_exit_code"
if [ $aws_test_exit_code -ne 0 ]; then
    echo "🔍 Debug: AWS CLI error output:"
    echo "$aws_test_output"
    echo ""
    
    # Try alternative tests
    echo "🔍 Debug: Trying alternative authentication methods..."
    
    # Test with environment variables only (no profile)
    echo "   Testing with environment variables only..."
    unset AWS_PROFILE
    env_test_output=$(AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" aws sts get-caller-identity 2>&1)
    env_test_exit_code=$?
    echo "   Environment test exit code: $env_test_exit_code"
    if [ $env_test_exit_code -ne 0 ]; then
        echo "   Environment test error: $env_test_output"
    else
        echo "   ✅ Environment variables work! Issue is with profile configuration."
        aws_identity="$env_test_output"
        aws_test_exit_code=0
    fi
    
    # Test profile configuration
    if [ $env_test_exit_code -ne 0 ]; then
        echo ""
        echo "   Checking profile configuration..."
        echo "   Profile config location: ~/.aws/config"
        echo "   Credentials location: ~/.aws/credentials"
        
        # Show what's actually configured for this profile
        echo "   Current profile configuration:"
        aws configure list --profile "$AWS_PROFILE_NAME" 2>/dev/null || echo "   Profile '$AWS_PROFILE_NAME' not found in configuration"
        
        # Try to diagnose the issue
        echo ""
        echo "   Possible issues:"
        echo "   1. AWS CLI not installed or not in PATH"
        echo "   2. Invalid credentials from Isengard"
        echo "   3. Network/connectivity issues"
        echo "   4. Regional restrictions"
        echo "   5. Profile configuration corruption"
        
        # Reset AWS_PROFILE for consistency
        export AWS_PROFILE="$AWS_PROFILE_NAME"
    else
        # Reset AWS_PROFILE since environment variables worked
        export AWS_PROFILE="$AWS_PROFILE_NAME"
    fi
fi

if [ $aws_test_exit_code -eq 0 ]; then
    aws_identity="$aws_test_output"
    echo "✅ AWS credentials set successfully!"
    echo "   Identity: $(echo "$aws_identity" | jq -r '.Arn')"
    echo "   Account: $(echo "$aws_identity" | jq -r '.Account')"
    echo "   Profile: $AWS_PROFILE_NAME"
    echo "   Region: $AWS_REGION"
    echo ""
    echo "💡 Environment variables set:"
    echo "   AWS_ACCESS_KEY_ID (set)"
    echo "   AWS_SECRET_ACCESS_KEY (set)"
    echo "   AWS_SESSION_TOKEN (set)"
    echo "   AWS_PROFILE=$AWS_PROFILE_NAME"
    echo ""
    echo "🎯 You can now run AWS CLI commands or deploy scripts with:"
    echo "   ./scripts/deploy.sh --profile $AWS_PROFILE_NAME --region $AWS_REGION deploy"
else
    echo "❌ Error: AWS credentials test failed"
    echo ""
    echo "🔧 Troubleshooting steps:"
    echo "   1. Verify AWS CLI is installed: aws --version"
    echo "   2. Check if you can access this account: aws sts get-caller-identity --profile $AWS_PROFILE_NAME"
    echo "   3. Try refreshing midway session: mwinit"
    echo "   4. Check account permissions in Isengard"
    echo "   5. Try a different region: --region us-east-1"
    echo ""
    echo "   Raw credentials object for debugging:"
    echo "   $credentials"
    exit 1
fi
