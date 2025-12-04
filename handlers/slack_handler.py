"""
Slack Events API handler for Zarathustra API.

Handles Slack Events API payloads including:
- URL verification challenge (for app setup)
- Message events (app_mention, message)

Slack Events API payload format:
- URL Verification: {"type": "url_verification", "challenge": "...", "token": "..."}
- Event Callback: {"type": "event_callback", "event": {"type": "message", "text": "...", ...}}
"""

import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import boto3

from models.schemas import SqsMessage
from utils.response import create_response, handle_error


# Lazy initialization of SQS client
_sqs_client = None


def get_sqs_client():
    """Get or create SQS client with lazy initialization."""
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client('sqs')
    return _sqs_client


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: str,
    signature: str
) -> bool:
    """
    Verify that the request came from Slack.
    
    Args:
        signing_secret: Slack app signing secret
        timestamp: X-Slack-Request-Timestamp header
        body: Raw request body
        signature: X-Slack-Signature header
        
    Returns:
        True if signature is valid
    """
    # Check timestamp to prevent replay attacks (5 minutes tolerance)
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    
    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body}"
    expected_signature = 'v0=' + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


def extract_message_text(event_data: Dict[str, Any]) -> Optional[str]:
    """
    Extract the message text from Slack event.
    
    Handles both regular messages and app mentions.
    Removes bot mention prefix if present.
    """
    text = event_data.get('text', '')
    
    # Remove bot mention (format: <@UXXXXXXXX>)
    if text.startswith('<@'):
        # Find the end of the mention
        end_idx = text.find('>')
        if end_idx != -1:
            text = text[end_idx + 1:].strip()
    
    return text if text else None


def handle_slack_event(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle Slack Events API webhook.
    
    Slack Events API payload types:
    1. url_verification - Challenge request for app setup
    2. event_callback - Actual event (message, app_mention, etc.)
    
    Supported event types:
    - message: Direct message or channel message
    - app_mention: When the bot is @mentioned
    """
    try:
        # Parse request body
        body = event.get('body', '')
        if isinstance(body, str):
            body_dict = json.loads(body)
        else:
            body_dict = body
        
        # Get headers for signature verification
        headers = event.get('headers', {})
        # API Gateway may lowercase headers
        slack_signature = headers.get('X-Slack-Signature') or headers.get('x-slack-signature', '')
        slack_timestamp = headers.get('X-Slack-Request-Timestamp') or headers.get('x-slack-request-timestamp', '')
        
        # Verify Slack signature if signing secret is configured
        signing_secret = os.environ.get('SLACK_SIGNING_SECRET')
        if signing_secret and slack_signature and slack_timestamp:
            raw_body = event.get('body', '')
            if isinstance(raw_body, dict):
                raw_body = json.dumps(raw_body)
            
            if not verify_slack_signature(signing_secret, slack_timestamp, raw_body, slack_signature):
                print("Slack signature verification failed")
                return create_response(
                    status_code=401,
                    message="Invalid request signature"
                )
        
        # Handle URL verification challenge (Slack app setup)
        if body_dict.get('type') == 'url_verification':
            challenge = body_dict.get('challenge', '')
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/plain'},
                'body': challenge
            }
        
        # Handle event callbacks
        if body_dict.get('type') == 'event_callback':
            event_data = body_dict.get('event', {})
            event_type = event_data.get('type', '')
            
            # Skip bot messages to prevent loops
            if event_data.get('bot_id') or event_data.get('subtype') == 'bot_message':
                return create_response(
                    status_code=200,
                    message="Bot message ignored"
                )
            
            # Handle message and app_mention events
            if event_type in ('message', 'app_mention'):
                message_text = extract_message_text(event_data)
                
                if not message_text:
                    return create_response(
                        status_code=200,
                        message="Empty message ignored"
                    )
                
                # Build metadata from Slack event
                metadata = {
                    'slack_team_id': body_dict.get('team_id'),
                    'slack_channel': event_data.get('channel'),
                    'slack_user': event_data.get('user'),
                    'slack_ts': event_data.get('ts'),
                    'slack_event_ts': event_data.get('event_ts'),
                    'slack_event_type': event_type,
                    'slack_channel_type': event_data.get('channel_type'),
                    'slack_thread_ts': event_data.get('thread_ts'),
                }
                
                # Generate message ID
                message_id = str(uuid.uuid4())
                
                # Build SQS message
                sqs_message = SqsMessage(
                    message_id=message_id,
                    prompt=message_text,
                    source='slack',
                    callback_url=None,  # Slack responses are sent via API
                    metadata=metadata,
                    timestamp=datetime.utcnow().isoformat()
                )
                
                # Get queue URL
                queue_url = os.environ.get('SQS_QUEUE_URL')
                if not queue_url:
                    return create_response(
                        status_code=500,
                        message="SQS queue URL not configured"
                    )
                
                # Send to SQS
                response = get_sqs_client().send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(sqs_message.model_dump(), default=str),
                    MessageAttributes={
                        'source': {
                            'DataType': 'String',
                            'StringValue': 'slack'
                        },
                        'message_id': {
                            'DataType': 'String',
                            'StringValue': message_id
                        },
                        'slack_channel': {
                            'DataType': 'String',
                            'StringValue': event_data.get('channel', 'unknown')
                        }
                    }
                )
                
                print(f"Slack message queued: {message_id}, SQS: {response.get('MessageId')}")
                
                # Slack expects 200 OK within 3 seconds
                return create_response(
                    status_code=200,
                    data={
                        'message_id': message_id,
                        'status': 'queued'
                    },
                    message="Message queued for processing"
                )
            
            # Unknown event type
            return create_response(
                status_code=200,
                message=f"Event type '{event_type}' not handled"
            )
        
        # Unknown payload type
        return create_response(
            status_code=400,
            message=f"Unknown payload type: {body_dict.get('type')}"
        )
        
    except json.JSONDecodeError:
        return create_response(
            status_code=400,
            message="Invalid JSON in request body"
        )
    except Exception as e:
        print(f"Error in handle_slack_event: {str(e)}")
        return handle_error(e, 500)
