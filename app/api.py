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
    status: Literal["done", "pending_clarification"]
    answer: Optional[str] = None
    question: Optional[str] = None               # pending_clarification 时:要问用户的话
    options: Optional[list] = None               # pending_clarification 时:可选项(有则前端渲染按钮)
    ticket_id: Optional[int] = None              # 开了退款工单时:单号,前端据此轮询结果回推

class ResumeRequest(BaseModel):
    session_id: str
    value: str        # 用户对挂起点(澄清追问)的补充回答;走 Command(resume=value)

def _to_response(result: dict) -> ChatResponse:
    """invoke 结果 → HTTP 响应。/chat 与 /resume 共用。
    interrupt 现在只有【澄清追问】一种(退款已工单化,不再走 interrupt 审批)。"""
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value   # 澄清追问:问题+可选项交前端,答完走 /resume 回来
        return ChatResponse(status="pending_clarification",
                            question=payload.get("question"), options=payload.get("options"))
    return ChatResponse(status="done", answer=result.get("answer"), ticket_id=result.get("ticket_id"))

@app.post("/chat", response_model = ChatResponse)
def chat(req: ChatRequest):
    q = req.question
    s = req.session_id
    config = {"configurable": {"thread_id": s}}
    result = app_graph.invoke({"question": q, "session_id": s, "messages":[{"role": "user", "content": q}],"contexts": [], "answer": "","route": "", "decision": None}, config)
    return _to_response(result)
    
@app.post("/resume", response_model = ChatResponse)
def resume(req: ResumeRequest):
    """统一的挂起恢复口(facade):澄清追问的补充信息、审批的 yes/no 都走这里。
    底层都是 Command(resume=value) —— 值交给正在等待的那个 interrupt()。"""
    config = {"configurable": {"thread_id": req.session_id}}
    result = app_graph.invoke(Command(resume = req.value), config)
    return _to_response(result)