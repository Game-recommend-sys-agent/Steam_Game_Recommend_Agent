from fastapi import APIRouter
from .endpoints import chat, document, context

api_router = APIRouter()
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(document.router, tags=["documents"])
api_router.include_router(context.router, tags=["context"])