# Zarathustra API

AI Agent Gateway API that receives prompts from third-party applications (Slack, Telegram, Jira, etc.) and publishes them to an SQS queue for processing by AI agents.

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│   Slack     │     │                 │     │             │     │             │
│   Telegram  │────▶│  API Gateway    │────▶│   Lambda    │────▶│  SQS Queue  │
│   Jira      │     │  (API Key Auth) │     │   Handler   │     │             │
│   ...       │     │                 │     │             │     │             │
└─────────────┘     └─────────────────┘     └─────────────┘     └─────────────┘
                                                                       │
                                                                       ▼
                                                               ┌─────────────┐
                                                               │  AI Agent   │
                                                               │  (Consumer) │
                                                               └─────────────┘
```

## Project Structure

```
zarathustra-api/
├── handlers/               # Lambda functions
│   ├── prompt_handler.py   # Main prompt endpoint
│   ├── slack_handler.py    # Slack Events API endpoint
│   └── health_handler.py   # Health check endpoint
├── models/                 # Pydantic schemas
│   └── schemas.py
├── utils/                  # Shared utilities
│   └── response.py
├── .github/workflows/      # CI/CD
│   └── deploy.yaml
├── template.yaml           # AWS SAM template
├── samconfig.toml          # SAM configuration
├── requirements.txt        # Python dependencies
└── README.md
```

## API Endpoints

### POST /prompt (requires API Key)

Receives a prompt and publishes it to SQS for AI agent processing.

**Headers:**
- `X-API-Key`: Your API key (required)
- `Content-Type`: application/json

**Request Body:**
```json
{
  "prompt": "Your message or question for the AI agent",
  "source": "slack",
  "callback_url": "https://your-app.com/webhook/response",
  "metadata": {
    "user_id": "U123456",
    "channel_id": "C789012"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | Yes | The message/prompt text |
| `source` | string | Yes | Source application (slack, telegram, jira, etc.) |
| `callback_url` | string | No | URL to send the response back to |
| `metadata` | object | No | Additional context from the source |

**Response (202 Accepted):**
```json
{
  "success": true,
  "data": {
    "message_id": "550e8400-e29b-41d4-a716-446655440000",
    "sqs_message_id": "abc123",
    "status": "queued"
  },
  "message": "Prompt successfully queued for processing"
}
```

### POST /slack/command (Slack Slash Commands)

Receives Slack Slash Command requests (e.g., `/zara`). No API key required - uses Slack's signing secret.

**Usage:**
```
/zara <your message>
/zara create a secret called my-api-key
```

**Slack Slash Command Payload (form-urlencoded):**
```
command=/zara&text=create+a+secret&user_id=U123&channel_id=C456&response_url=https://...
```

**Response (200 OK):**
```json
{
  "response_type": "in_channel",
  "text": ":hourglass_flowing_sand: Processing your request...\n> create a secret"
}
```

**SQS Message Metadata (from Slash Command):**
```json
{
  "slack_team_id": "T123456",
  "slack_channel": "C789012",
  "slack_user": "U123456",
  "slack_command": "/zara",
  "slack_response_url": "https://hooks.slack.com/...",
  "slack_event_type": "slash_command"
}
```

### POST /slack/events (Slack Events API)

Receives Slack Events API webhooks. No API key required - uses Slack's signing secret for verification.

**Supported Events:**
- `message` - Direct messages or channel messages
- `app_mention` - When the bot is @mentioned

**Slack Event Payload:**
```json
{
  "type": "event_callback",
  "team_id": "T123456",
  "event": {
    "type": "app_mention",
    "user": "U123456",
    "text": "<@UBOT123> What is the weather?",
    "channel": "C789012",
    "ts": "1234567890.123456"
  }
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "queued"
  },
  "message": "Message queued for processing"
}
```

### GET /health (no auth required)

Health check endpoint.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "service": "zarathustra-api",
    "timestamp": "2024-01-15T10:30:00.000000"
  },
  "message": "Service is healthy"
}
```

## SQS Message Format

Messages published to SQS follow this schema:

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "prompt": "User's prompt text",
  "source": "slack",
  "callback_url": "https://your-app.com/webhook/response",
  "metadata": {
    "user_id": "U123456"
  },
  "timestamp": "2024-01-15T10:30:00.000000"
}
```

## Installation

### Prerequisites

- Python 3.12
- AWS CLI configured
- AWS SAM CLI installed

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start local API:
```bash
sam build
sam local start-api
```

3. Test locally:
```bash
curl -X POST http://localhost:3000/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello AI", "source": "test"}'
```

## Deployment

### Manual Deployment

```bash
# Build
sam build

# Deploy (first time - guided)
sam deploy --guided --profile depstacks

# Deploy (subsequent)
sam deploy --profile depstacks
```

### CI/CD Deployment

The project includes GitHub Actions workflow that deploys automatically on push to `main`.

**Required GitHub Variables:**
- `AWS_ROLE_ARN`: IAM role ARN for OIDC authentication
- `AWS_REGION`: AWS region (default: us-east-1)

### Get API Key

After deployment, retrieve the API key:

```bash
# Get API Key ID from CloudFormation outputs
API_KEY_ID=$(aws cloudformation describe-stacks \
  --stack-name zarathustra-api \
  --query 'Stacks[0].Outputs[?OutputKey==`ZarathustraApiKeyId`].OutputValue' \
  --output text \
  --profile depstacks)

# Get API Key value
aws apigateway get-api-key \
  --api-key $API_KEY_ID \
  --include-value \
  --query 'value' \
  --output text \
  --profile depstacks
```

## Testing

```bash
# Health check
curl https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/api/health

# Send prompt (requires API key)
curl -X POST https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/api/prompt \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "prompt": "What is the weather today?",
    "source": "slack",
    "callback_url": "https://my-app.com/webhook",
    "metadata": {"user": "john"}
  }'
```

## AWS Resources Created

| Resource | Name | Description |
|----------|------|-------------|
| API Gateway | zarathustra-api | REST API with API Key auth |
| Lambda | zarathustra-prompt-handler | Receives prompts and publishes to SQS |
| Lambda | zarathustra-slack-handler | Handles Slack Events API webhooks |
| Lambda | zarathustra-health-check | Health check endpoint |
| SQS Queue | zarathustra-agent-requests | Main queue for AI agent requests |
| SQS DLQ | zarathustra-agent-requests-dlq | Dead letter queue for failed messages |
| API Key | zarathustra-api-key | Authentication key |
| Usage Plan | zarathustra-api-usage-plan | Rate limiting and quota |

## Response Format

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "message": "Success message"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error description",
  "code": "400"
}
```

## Rate Limits

- **Daily Quota**: 10,000 requests
- **Rate Limit**: 50 requests/second
- **Burst Limit**: 100 requests

## Slack App Setup

To integrate with Slack:

### 1. Create a Slack App
1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name your app (e.g., "Zarathustra") and select a workspace

### 2. Configure Slash Commands
1. Navigate to "Slash Commands"
2. Click "Create New Command"
3. Configure:
   - **Command**: `/zara`
   - **Request URL**: `https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/api/slack/command`
   - **Short Description**: "AI Agent for AWS operations"
   - **Usage Hint**: `<your request>`
4. Save

### 3. Configure Event Subscriptions (Optional)
1. Navigate to "Event Subscriptions"
2. Enable Events
3. Set Request URL to: `https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/api/slack/events`
4. Subscribe to bot events:
   - `app_mention` - When someone @mentions your bot
   - `message.im` - Direct messages to your bot

### 4. Set Signing Secret
1. Go to "Basic Information" → "App Credentials"
2. Copy the "Signing Secret"
3. Deploy with the signing secret:
```bash
sam deploy --parameter-overrides SlackSigningSecret=your_signing_secret --profile depstacks
```

### 5. Install App to Workspace
1. Go to "OAuth & Permissions"
2. Add Bot Token Scopes:
   - `commands` - For slash commands
   - `chat:write` - To send messages
   - `app_mentions:read` (optional)
   - `im:history` (optional)
3. Install App to Workspace

### 6. Test Integration
Use the slash command in any channel:
```
/zara list all secrets in production
```

## License

MIT
