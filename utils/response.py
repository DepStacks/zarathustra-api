import json
from typing import Any, Dict, Optional

from models.schemas import ApiResponse, ErrorResponse


def create_response(
    status_code: int = 200,
    data: Any = None,
    message: Optional[str] = None,
    total_records: Optional[int] = None
) -> Dict[str, Any]:
    """Creates a standardized API response."""
    if status_code >= 400:
        response_body = ErrorResponse(
            error=message or "Internal server error",
            code=str(status_code)
        )
    else:
        response_body = ApiResponse(
            data=data,
            message=message,
            total_records=total_records
        )
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(response_body.model_dump(), default=str, ensure_ascii=False)
    }


def handle_error(error: Exception, status_code: int = 500) -> Dict[str, Any]:
    """Handles exceptions and returns error response."""
    error_message = str(error) if str(error) else "Internal server error"
    return create_response(
        status_code=status_code,
        message=error_message
    )
