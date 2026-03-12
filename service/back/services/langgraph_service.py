"""
LangGraph 기반 채팅 서비스.

그래프 구조:
  START → call_llm → END

세션 메모리:
  MemorySaver (인메모리 체크포인터) — thread_id = session_id 로 구분
"""

import asyncio
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState

from core.config import settings

_SYSTEM_MSG = SystemMessage(
    content="You are a helpful Steam game recommendation assistant."
)


class LangGraphService:
    def __init__(self):
        self._llm = ChatOpenAI(
            openai_api_key=settings.OPENAI_API_KEY,
            model="gpt-4o",
        )

        # ── 그래프 정의 ──────────────────────────────────────────
        graph = StateGraph(MessagesState)
        graph.add_node("call_llm", self._call_llm)
        graph.add_edge(START, "call_llm")
        graph.add_edge("call_llm", END)

        # MemorySaver: thread_id(= session_id) 단위로 대화 이력 유지
        self._app = graph.compile(checkpointer=MemorySaver())

    # ── 노드 ────────────────────────────────────────────────────
    def _call_llm(self, state: MessagesState) -> dict[str, Any]:
        messages = [_SYSTEM_MSG] + state["messages"]
        response = self._llm.invoke(messages)
        return {"messages": [response]}

    # ── 공개 인터페이스 ──────────────────────────────────────────
    async def add_document(self, _content: str, _metadata: dict):
        return None

    async def chat(self, query: str, session_id: str) -> dict[str, Any]:
        config = {"configurable": {"thread_id": session_id}}
        result = await asyncio.to_thread(
            self._app.invoke,
            {"messages": [HumanMessage(content=query)]},
            config,
        )
        answer = result["messages"][-1].content
        return {"answer": answer, "source_documents": []}
