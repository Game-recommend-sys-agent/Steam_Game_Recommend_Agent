import asyncio
from typing import Dict

from langchain_openai import ChatOpenAI
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from core.config import settings

# 세션별 인메모리 히스토리 저장소
_session_store: Dict[str, InMemoryChatMessageHistory] = {}


class LangChainService:
    def __init__(self):
        self.llm = ChatOpenAI(openai_api_key=settings.OPENAI_API_KEY, model="gpt-4o")

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful Steam game recommendation assistant."),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ])

        chain = (
            RunnablePassthrough.assign(source_documents=lambda _: [])
            | RunnablePassthrough.assign(
                answer=(prompt | self.llm | StrOutputParser()),
            )
        )

        self._chain_with_history = RunnableWithMessageHistory(
            chain,
            self._get_message_history,
            input_messages_key="question",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )

    def _get_message_history(self, session_id: str) -> InMemoryChatMessageHistory:
        if session_id not in _session_store:
            _session_store[session_id] = InMemoryChatMessageHistory()
        return _session_store[session_id]

    async def add_document(self, _content: str, _metadata: dict):
        return None

    async def chat(self, query: str, session_id: str):
        result = await asyncio.to_thread(
            self._chain_with_history.invoke,
            {"question": query},
            {"configurable": {"session_id": session_id}},
        )
        return {
            "answer": result["answer"],
            "source_documents": result.get("source_documents", []),
        }
