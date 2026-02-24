"""Chat endpoints - RAG-powered conversations with Claude."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter()


class ChatMessage(BaseModel):
    """A single message in the conversation."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=10000)


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str = Field(..., min_length=1, max_length=5000)
    conversation_id: str | None = None
    conversation_history: list[ChatMessage] = Field(default_factory=list, max_length=50)
    country_code: str = Field(default="cl", pattern="^[a-z]{2}$")
    stream: bool = True


class ChatResponse(BaseModel):
    """Response body for non-streaming chat."""

    message: str
    conversation_id: str
    citations: list[dict]
    tokens_used: int


class ConversationInfo(BaseModel):
    """Basic conversation information."""

    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


@router.post("")
async def chat(request: ChatRequest):
    """
    Send a message and get a response from ELECTRIA.

    Uses RAG to retrieve relevant documents and Claude to generate responses.
    Supports streaming responses for real-time output.
    """
    # TODO: Implement full RAG pipeline
    # 1. Retrieve relevant chunks from Pinecone
    # 2. Rerank with Cohere
    # 3. Generate response with Claude
    # 4. Save to conversation history
    # 5. Log usage

    if request.stream:
        async def generate():
            # Placeholder streaming response
            response = f"[ELECTRIA] Recibí tu pregunta: '{request.message}'. El sistema RAG aún está en desarrollo."
            for char in response:
                yield char

        return StreamingResponse(
            generate(),
            media_type="text/plain",
        )
    else:
        return ChatResponse(
            message=f"[ELECTRIA] Recibí tu pregunta: '{request.message}'. El sistema RAG aún está en desarrollo.",
            conversation_id=request.conversation_id or "new-conversation-id",
            citations=[],
            tokens_used=0,
        )


@router.get("/conversations")
async def list_conversations(
    limit: int = 20,
    offset: int = 0,
) -> list[ConversationInfo]:
    """List user's conversations."""
    # TODO: Implement with auth
    return []


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict:
    """Get a specific conversation with all messages."""
    # TODO: Implement
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict:
    """Delete a conversation."""
    # TODO: Implement
    return {"deleted": True}
