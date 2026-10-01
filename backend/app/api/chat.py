"""
Chat API routes for QueryPilot.
Handles conversational queries, clarifications, and conversation management.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.chat import (
    ChatMessage,
    ChatRequest,
    ClarifyRequest,
    ConversationContext,
    QueryIntent,
)
from app.models.schema import QueryResult
from app.services.database.session_manager import session_manager
from app.services.pipeline import QueryPipeline

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# In-memory conversation store
_conversations: dict[str, ConversationContext] = {}

# Shared pipeline instance
_pipeline = QueryPipeline()


# --- Response Models ---

class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    has_clarification: bool = False


class ConversationResponse(BaseModel):
    conversation_id: str
    database_id: str
    message_count: int
    messages: list[ChatMessage]


# --- Helper Functions ---

def _get_or_create_conversation(
    conversation_id: Optional[str],
    database_id: str,
) -> ConversationContext:
    """Get existing conversation or create a new one."""
    if conversation_id and conversation_id in _conversations:
        ctx = _conversations[conversation_id]
        # Validate same database
        if ctx.database_id != database_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot switch databases within the same conversation. Start a new conversation.",
            )
        return ctx

    # Create new conversation
    new_id = conversation_id or uuid.uuid4().hex[:16]
    ctx = ConversationContext(
        conversation_id=new_id,
        database_id=database_id,
    )
    _conversations[new_id] = ctx
    return ctx


# --- Endpoints ---

@router.post("", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """Send a natural-language query and receive a response."""
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    database_id = request.database_id
    if not database_id:
        raise HTTPException(status_code=400, detail="database_id (session_id) is required.")

    # Verify session exists
    session = session_manager.get_session(database_id)
    if not session:
        raise HTTPException(status_code=404, detail="Database session not found or expired. Please reconnect.")

    if not session.schema:
        raise HTTPException(status_code=500, detail="Database schema not available.")

    # Get or create conversation
    conversation = _get_or_create_conversation(request.conversation_id, database_id)

    # Record user message
    user_msg = ChatMessage(
        id=uuid.uuid4().hex[:12],
        role="user",
        content=request.query.strip(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    conversation.messages.append(user_msg)

    # Run pipeline
    response_msg = await _pipeline.process_query(
        query=request.query.strip(),
        conversation=conversation,
        schema=session.schema,
        adapter=session.adapter,
    )

    # Record assistant message
    conversation.messages.append(response_msg)

    return ChatResponse(
        conversation_id=conversation.conversation_id,
        message=response_msg,
        has_clarification=response_msg.clarification is not None,
    )


@router.post("/{conversation_id}/clarify", response_model=ChatResponse)
async def clarify(conversation_id: str, request: ClarifyRequest):
    """Respond to a clarification question."""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    conversation = _conversations[conversation_id]

    # Verify session
    session = session_manager.get_session(conversation.database_id)
    if not session:
        raise HTTPException(status_code=404, detail="Database session expired. Please reconnect.")

    if not conversation.pending_clarification:
        raise HTTPException(
            status_code=400,
            detail="No pending clarification in this conversation.",
        )

    # Record clarification as user message
    answer_text = request.custom_input or request.selected_option
    user_msg = ChatMessage(
        id=uuid.uuid4().hex[:12],
        role="user",
        content=answer_text,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    conversation.messages.append(user_msg)

    # Run clarification pipeline
    response_msg = await _pipeline.process_clarification(
        clarify_request=request,
        conversation=conversation,
        schema=session.schema,
        adapter=session.adapter,
    )

    # Record assistant response
    conversation.messages.append(response_msg)

    return ChatResponse(
        conversation_id=conversation.conversation_id,
        message=response_msg,
        has_clarification=response_msg.clarification is not None,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    """Retrieve conversation history."""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    ctx = _conversations[conversation_id]
    return ConversationResponse(
        conversation_id=ctx.conversation_id,
        database_id=ctx.database_id,
        message_count=len(ctx.messages),
        messages=ctx.messages,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    del _conversations[conversation_id]
    return {"message": "Conversation deleted.", "conversation_id": conversation_id}
