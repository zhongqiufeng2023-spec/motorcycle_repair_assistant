import os
import jwt
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from langgraph.types import Command
from app.agents import app_graph

app = FastAPI(title="摩托车智能助手")

# JWT 校验:与 Spring Boot 共享【同一把密钥 + 算法】(无状态,不共享 session)。
# 密钥 53 字节 → jjwt 用 HS384 签,故这里也用 HS384。生产用 JWT_SECRET 环境变量覆盖。
JWT_SECRET = os.getenv("JWT_SECRET", "moto-dev-jwt-secret-change-me-please-0123456789abcdef")
JWT_ALG = "HS384"


def current_user_id(authorization: str = Header(default=None)) -> str:
    """验 Authorization: Bearer <jwt>,返回 user_id(令牌 sub)。缺失/无效/过期 → 401。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要登录")
    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="登录已失效,请重新登录")
    return payload["sub"]   # sub = userId 字符串(Spring Boot 签发时放的)


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
def chat(req: ChatRequest, user_id: str = Depends(current_user_id)):
    q = req.question
    s = req.session_id
    config = {"configurable": {"thread_id": s}}
    # user_id 由验过的 JWT 取出、注入 state(和 session_id 一路):开退款工单时绑到这个用户
    result = app_graph.invoke({"question": q, "session_id": s, "user_id": user_id,
                               "messages":[{"role": "user", "content": q}],
                               "contexts": [], "answer": "","route": "", "decision": None}, config)
    return _to_response(result)

@app.post("/resume", response_model = ChatResponse)
def resume(req: ResumeRequest, user_id: str = Depends(current_user_id)):
    """挂起恢复口(澄清追问的补充信息走这)。user_id 已随首次 /chat 存进 checkpoint,
    这里只做登录闸门,不必重复注入(Command(resume) 续跑的是已存档的 state)。"""
    config = {"configurable": {"thread_id": req.session_id}}
    result = app_graph.invoke(Command(resume = req.value), config)
    return _to_response(result)
