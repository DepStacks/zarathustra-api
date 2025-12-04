from datetime import datetime
from typing import Any, Dict

from utils.response import create_response


def health_check(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Health check endpoint to verify the API is running.
    """
    return create_response(
        status_code=200,
        data={
            'status': 'healthy',
            'service': 'zarathustra-api',
            'timestamp': datetime.utcnow().isoformat()
        },
        message="Service is healthy"
    )
