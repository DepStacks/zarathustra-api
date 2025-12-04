import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict

import boto3

from models.schemas import PromptRequest, SqsMessage
from utils.response import create_response, handle_error


# Lazy initialization of SQS client
_sqs_client = None


def get_sqs_client():
    """Get or create SQS client with lazy initialization."""
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client('sqs')
    return _sqs_client


def handle_prompt(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Receives a prompt request from third-party apps and publishes to SQS queue.
    
    Expected JSON body:
    {
        "prompt": "User message/prompt text",
        "source": "slack|telegram|jira|...",
        "callback_url": "URL to send response (optional)",
        "metadata": { ... }  (optional)
    }
    """
    try:
        # Parse request body
        body = event.get('body')
        if not body:
            return create_response(
                status_code=400,
                message="Request body is required"
            )
        
        if isinstance(body, str):
            body = json.loads(body)
        
        # Validate request
        try:
            request = PromptRequest(**body)
        except Exception as validation_error:
            return create_response(
                status_code=400,
                message=f"Invalid request: {str(validation_error)}"
            )
        
        # Generate message ID
        message_id = str(uuid.uuid4())
        
        # Build SQS message
        sqs_message = SqsMessage(
            message_id=message_id,
            prompt=request.prompt,
            source=request.source,
            callback_url=request.callback_url,
            metadata=request.metadata or {},
            timestamp=datetime.utcnow().isoformat()
        )
        
        # Get queue URL from environment
        queue_url = os.environ.get('SQS_QUEUE_URL')
        if not queue_url:
            return create_response(
                status_code=500,
                message="SQS queue URL not configured"
            )
        
        # Send message to SQS
        response = get_sqs_client().send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(sqs_message.model_dump(), default=str),
            MessageAttributes={
                'source': {
                    'DataType': 'String',
                    'StringValue': request.source
                },
                'message_id': {
                    'DataType': 'String',
                    'StringValue': message_id
                }
            }
        )
        
        return create_response(
            status_code=202,
            data={
                'message_id': message_id,
                'sqs_message_id': response.get('MessageId'),
                'status': 'queued'
            },
            message="Prompt successfully queued for processing"
        )
        
    except json.JSONDecodeError:
        return create_response(
            status_code=400,
            message="Invalid JSON in request body"
        )
    except Exception as e:
        print(f"Error in handle_prompt: {str(e)}")
        return handle_error(e, 500)
