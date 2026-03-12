from fastapi import APIRouter, HTTPException
from schemas.document import DocumentRequest, DocumentResponse
from services.langchain import LangChainService

router = APIRouter()
service = LangChainService()


@router.post("/documents", response_model=DocumentResponse)
async def add_document(request: DocumentRequest):
    try:
        doc_id = await service.add_document(request.content, request.metadata)
        return DocumentResponse(id=str(doc_id), status="created")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
