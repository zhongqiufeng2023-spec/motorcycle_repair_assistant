from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal, Optional
from langgraph.types import Command
from app.agents import app_graph

app = FastAPI(title="摩托车智能助手")

class ChatRequest(BaseModel):
    session_id : str
    question: str

class ChatResponse(BaseModel):
    status:Literal["done","pending_approval"]
    answer:Optional[str] = None
    approval_request : Optional[dict] = None 

class ApproveRequest(BaseModel):
    session_id: str
    decision: Literal["yes", "no"]

def _to_response(result: dict) -> ChatResponse:
    """invoke 结果 → HTTP 响应。/chat 和 /approve 共用(同一套判断,抽出来)"""
    if "__interrupt__" in result:
        return ChatResponse(status="pending_approval",approval_request=result["__interrupt__"][0].value)
    return ChatResponse(status="done", answer=result.get("answer"))

@app.post("/chat", response_model = ChatResponse)
def chat(req: ChatRequest):
    q = req.question
    s = req.session_id
    config = {"configurable": {"thread_id": s}}
    result = app_graph.invoke({"question": q, "messages":[{"role": "user", "content": q}],"contexts": [], "answer": "","route": "", "decision": None}, config)
    return _to_response(result)
    
@app.post("/approve", response_model = ChatResponse)
def approve(req: ApproveRequest):
    config = {"configurable": {"thread_id": req.session_id}}
    result = app_graph.invoke(Command(resume = req.decision), config)
    return _to_response(result)