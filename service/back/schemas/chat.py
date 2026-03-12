from pydantic import BaseModel
from typing import List, Dict, Any


class ChatRequest(BaseModel):
    query: str
    session_id: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    session_id: str
