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
    status: Literal["done", "pending_approval", "pending_clarification"]
    answer: Optional[str] = None
    approval_request: Optional[dict] = None      # pending_approval 时:退款审批详情
    question: Optional[str] = None               # pending_clarification 时:要问用户的话
    options: Optional[list] = None               # pending_clarification 时:可选项(有则前端渲染按钮)

class ResumeRequest(BaseModel):
    session_id: str
    value: str        # 用户对挂起点的回答:澄清=补充信息;审批=yes/no。统一走 Command(resume=value)

class ApproveRequest(BaseModel):
    session_id: str
    decision: Literal["yes", "no"]

def _to_response(result: dict) -> ChatResponse:
    """invoke 结果 → HTTP 响应。/chat 与 /resume 共用。按 interrupt 的 type 分流两种挂起。"""
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        if payload.get("type") == "clarify":
            # 澄清追问:把问题(和可选项)交给前端,用户答完走 /resume 回来
            return ChatResponse(status="pending_clarification",
                                question=payload.get("question"), options=payload.get("options"))
        # 退款审批(一期 interrupt 老模型,待工单化替换)
        return ChatResponse(status="pending_approval",
                            answer="您的退款申请已提交,正在等待商家审核,请勿重复发起。",
                            approval_request=payload)
    return ChatResponse(status="done", answer=result.get("answer"))

@app.post("/chat", response_model = ChatResponse)
def chat(req: ChatRequest):
    q = req.question
    s = req.session_id
    config = {"configurable": {"thread_id": s}}
    result = app_graph.invoke({"question": q, "messages":[{"role": "user", "content": q}],"contexts": [], "answer": "","route": "", "decision": None}, config)
    return _to_response(result)
    
@app.post("/resume", response_model = ChatResponse)
def resume(req: ResumeRequest):
    """统一的挂起恢复口(facade):澄清追问的补充信息、审批的 yes/no 都走这里。
    底层都是 Command(resume=value) —— 值交给正在等待的那个 interrupt()。"""
    config = {"configurable": {"thread_id": req.session_id}}
    result = app_graph.invoke(Command(resume = req.value), config)
    return _to_response(result)

@app.post("/approve", response_model = ChatResponse)
def approve(req: ApproveRequest):
    # 退款审批专用别名(语义清晰);底层与 /resume 相同。退款工单化后此端点将下线。
    config = {"configurable": {"thread_id": req.session_id}}
    result = app_graph.invoke(Command(resume = req.decision), config)
    return _to_response(result)