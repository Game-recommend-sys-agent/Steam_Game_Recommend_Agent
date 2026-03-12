from pydantic import BaseModel
from typing import Dict, Any

class DocumentRequest(BaseModel):
    content: str
    metadata: Dict[str, Any] = {}

class DocumentResponse(BaseModel):
    id: str
    status: str
