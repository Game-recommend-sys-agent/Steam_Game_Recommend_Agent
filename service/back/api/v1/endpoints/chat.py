import uuid
from fastapi import APIRouter, HTTPException
from schemas.chat import ChatRequest, ChatResponse
from services.langgraph_service import LangGraphService

router = APIRouter()
service = LangGraphService()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        session_id = request.session_id or str(uuid.uuid4())
        result = await service.chat(request.query, session_id)
        sources = [doc.metadata for doc in result.get("source_documents", [])]
        return ChatResponse(answer=result["answer"], sources=sources, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
