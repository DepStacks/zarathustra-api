"""
Slack handler for Zarathustra API.

Handles:
1. Slack Slash Commands (e.g., /zara) - form-urlencoded payload
2. Slack Events API - JSON payload
   - URL verification challenge (for app setup)
   - Message events (app_mention, message)

Slash Command payload (form-urlencoded):
- command=/zara, text=hello world, user_id=U123, channel_id=C456, response_url=...

Events API payload (JSON):
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
from urllib.parse import parse_qs

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


def is_slash_command(body: str) -> bool:
    """Check if the request body is a slash command (form-urlencoded)."""
    # Slash commands contain 'command=' in the body
    return 'command=' in body and 'text=' in body


def parse_slash_command(body: str) -> Dict[str, str]:
    """Parse form-urlencoded slash command payload."""
    parsed = parse_qs(body)
    # parse_qs returns lists, extract first value
    return {k: v[0] if v else '' for k, v in parsed.items()}


def handle_slash_command(
    command_data: Dict[str, str],
    event: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle Slack slash command.
    
    Slash command payload fields:
    - command: The slash command (e.g., /zara)
    - text: Text after the command
    - user_id: User who invoked the command
    - user_name: Username
    - channel_id: Channel where command was invoked
    - channel_name: Channel name
    - team_id: Team ID
    - team_domain: Team domain
    - response_url: URL for delayed responses
    - trigger_id: For opening modals
    """
    command = command_data.get('command', '')
    text = command_data.get('text', '').strip()
    
    if not text:
        # Return immediate response for empty command
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'response_type': 'ephemeral',
                'text': f'Usage: `{command} <your message>`\nExample: `{command} create a secret called my-api-key`'
            })
        }
    
    # Build metadata from slash command
    metadata = {
        'slack_team_id': command_data.get('team_id'),
        'slack_team_domain': command_data.get('team_domain'),
        'slack_channel': command_data.get('channel_id'),
        'slack_channel_name': command_data.get('channel_name'),
        'slack_user': command_data.get('user_id'),
        'slack_user_name': command_data.get('user_name'),
        'slack_command': command,
        'slack_response_url': command_data.get('response_url'),
        'slack_trigger_id': command_data.get('trigger_id'),
        'slack_event_type': 'slash_command',
    }
    
    # Generate message ID
    message_id = str(uuid.uuid4())
    
    # Build SQS message
    sqs_message = SqsMessage(
        message_id=message_id,
        prompt=text,
        source='slack',
        callback_url=command_data.get('response_url'),  # Use response_url for callbacks
        metadata=metadata,
        timestamp=datetime.utcnow().isoformat()
    )
    
    # Get queue URL
    queue_url = os.environ.get('SQS_QUEUE_URL')
    if not queue_url:
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'response_type': 'ephemeral',
                'text': ':x: Error: Service not configured properly. Please contact the administrator.'
            })
        }
    
    # Send to SQS
    try:
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
                    'StringValue': command_data.get('channel_id', 'unknown')
                },
                'slack_command': {
                    'DataType': 'String',
                    'StringValue': command
                }
            }
        )
        
        print(f"Slack slash command queued: {message_id}, SQS: {response.get('MessageId')}")
        
        # Return immediate acknowledgment to Slack
        # The actual response will be sent via response_url by the agent
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'response_type': 'in_channel',
                'text': f':hourglass_flowing_sand: Processing your request...\n> {text}'
            })
        }
        
    except Exception as e:
        print(f"Error sending to SQS: {e}")
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'response_type': 'ephemeral',
                'text': f':x: Error queuing request: {str(e)}'
            })
        }


def handle_slack_event(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle Slack requests (both slash commands and Events API).
    
    Supported request types:
    1. Slash Commands (form-urlencoded) - /zara <message>
    2. Events API (JSON):
       - url_verification - Challenge request for app setup
       - event_callback - message, app_mention events
    """
    try:
        # Get raw body
        raw_body = event.get('body', '')
        
        # Check if this is a slash command (form-urlencoded)
        if isinstance(raw_body, str) and is_slash_command(raw_body):
            print(f"Processing slash command")
            
            # Verify signature first
            headers = event.get('headers', {})
            slack_signature = headers.get('X-Slack-Signature') or headers.get('x-slack-signature', '')
            slack_timestamp = headers.get('X-Slack-Request-Timestamp') or headers.get('x-slack-request-timestamp', '')
            signing_secret = os.environ.get('SLACK_SIGNING_SECRET')
            
            if signing_secret and slack_signature and slack_timestamp:
                if not verify_slack_signature(signing_secret, slack_timestamp, raw_body, slack_signature):
                    print("Slack signature verification failed for slash command")
                    return {
                        'statusCode': 401,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({'error': 'Invalid signature'})
                    }
            
            # Parse and handle slash command
            command_data = parse_slash_command(raw_body)
            return handle_slash_command(command_data, event)
        
        # Parse JSON body for Events API
        body = raw_body
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
