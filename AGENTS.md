# Zarathustra API - Agent Guidelines

## Project Overview

This is an AWS SAM serverless project that serves as an AI Agent Gateway. It receives prompts from third-party applications and publishes them to SQS for processing.

## Architecture Mandates

### File Structure
```
zarathustra-api/
├── handlers/           # Lambda function handlers
├── models/             # Pydantic schemas
├── utils/              # Shared utilities
├── template.yaml       # AWS SAM template
├── samconfig.toml      # SAM configuration
└── requirements.txt    # Python dependencies
```

### Code Conventions

1. **Python Version**: Use Python 3.12
2. **Type Hints**: Always use type hints for function parameters and return values
3. **Pydantic**: Use Pydantic v2 for data validation
4. **Response Format**: Always use `utils/response.py` for API responses

### Lambda Handler Pattern

```python
from typing import Any, Dict
from utils.response import create_response, handle_error

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        # Handler logic
        return create_response(status_code=200, data=result)
    except Exception as e:
        return handle_error(e, 500)
```

### SAM Template Conventions

1. **Stage Name**: Use `api` as the single stage name
2. **Function Naming**: Use pattern `zarathustra-{function-name}`
3. **Queue Naming**: Use pattern `zarathustra-{queue-name}`
4. **Region**: Default to `us-east-1`

### Security Requirements

1. **API Key Authentication**: Required for data endpoints, optional for health checks
2. **IAM Policies**: Use least privilege principle
3. **No hardcoded secrets**: Use environment variables or AWS Secrets Manager

### Documentation

1. Keep documentation in `README.md` only
2. Update `AGENTS.md` for AI agent instructions
3. Do not create additional markdown files

### Git Conventions

1. **Branch**: Work on `main` branch (single environment)
2. **Commits**: Use conventional commits format
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation
   - `refactor:` for code refactoring

### Deployment

1. **Profile**: Use AWS profile `depstacks`
2. **Region**: Deploy to `us-east-1`
3. **CI/CD**: GitHub Actions workflow deploys on push to `main`

## Adding New Endpoints

1. Create handler in `handlers/` directory
2. Add Pydantic schemas in `models/schemas.py`
3. Add Lambda function in `template.yaml`
4. Update `README.md` with endpoint documentation

## Third-Party Integrations

### Slack Integration
- Handler: `handlers/slack_handler.py`
- Auth: Slack Signing Secret (not API Key)

**Endpoints:**
- `POST /slack/command` - Slash commands (e.g., `/zara`)
- `POST /slack/events` - Events API (app_mention, message)

**Slash Command Payload (form-urlencoded):**
- Parsed with `urllib.parse.parse_qs`
- Key fields: `command`, `text`, `user_id`, `channel_id`, `response_url`
- `response_url` is stored in SQS metadata for async responses

**Events API Payload (JSON):**
- `url_verification` for app setup
- `event_callback` for messages

## Testing

```bash
# Build
sam build

# Local API
sam local start-api

# Deploy
sam deploy --profile depstacks
```
