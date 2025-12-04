from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PromptRequest(BaseModel):
    """Request schema for prompt endpoint."""
    prompt: str = Field(..., description="The prompt text to send to the AI agent")
    source: str = Field(..., description="Source application (e.g., slack, telegram, jira)")
    callback_url: Optional[str] = Field(None, description="URL to send the response back to")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata from the source")


class SqsMessage(BaseModel):
    """Schema for SQS message payload."""
    message_id: str = Field(..., description="Unique message identifier")
    prompt: str = Field(..., description="The prompt text")
    source: str = Field(..., description="Source application")
    callback_url: Optional[str] = Field(None, description="Callback URL for response")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: str = Field(..., description="ISO timestamp when message was received")


class ApiResponse(BaseModel):
    """Standard API success response."""
    success: bool = True
    data: Any = None
    message: Optional[str] = None
    total_records: Optional[int] = None


class ErrorResponse(BaseModel):
    """Standard API error response."""
    success: bool = False
    error: str
    code: str
