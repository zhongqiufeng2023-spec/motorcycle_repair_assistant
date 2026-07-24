"""Agent 侧的 MCP 客户端 —— 把 async 的 fastmcp Client 桥成 action_node 能直接用的【同步】接口。

为什么要桥:action_node 是 def(同步),主流水线刻意不上 async(async 有传染性,见 D9 坑7)。
           fastmcp Client 是 async,所以在这里用 asyncio.run 把每次调用桥成同步——async 被关在本模块内。
线程安全:  action_node 跑在 FastAPI 的线程池线程里(sync handler),该线程没有运行中的事件循环,
           asyncio.run 可以安全地新建/关闭一个循环。若哪天 action_node 改成在事件循环内跑,这里要改持久循环。
v1 取舍:  每次调用新建连接(简单直白);要低延迟/高并发再换"持久连接 + 常驻事件循环"。
"""
import os, asyncio
from fastmcp import Client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:9000/mcp")

# 系统注入、不该进 LLM 视野的参数:发给 LLM 的 schema 里剥掉,由 action_node 在 call() 前注入。
_SYSTEM_PARAMS = {"session_id", "user_id"}


async def _alist():
    async with Client(MCP_URL) as c:
        return await c.list_tools()


async def _acall(name: str, args: dict):
    async with Client(MCP_URL) as c:
        r = await c.call_tool(name, args)
        return r.data          # 工具返回的 dict(我们的工具统一 {"ok":...} 契约)


def get_tool_schemas() -> list:
    """tools/list → 转成 openai function-calling 的 tools 格式,并剥掉系统参数(如 session_id)。
    连不上工具服务会抛异常(fail-loud):agent 处理业务请求必须要有工具服务在。"""
    schemas = []
    for t in asyncio.run(_alist()):
        params = dict(t.inputSchema or {"type": "object", "properties": {}})
        props = {k: v for k, v in params.get("properties", {}).items() if k not in _SYSTEM_PARAMS}
        required = [r for r in params.get("required", []) if r not in _SYSTEM_PARAMS]
        params = {**params, "properties": props, "required": required}
        schemas.append({"type": "function",
                        "function": {"name": t.name, "description": t.description, "parameters": params}})
    return schemas


def call(name: str, args: dict) -> dict:
    """tools/call → 返回结果 dict。同步接口。任何调用层失败(连不上/未知工具/参数非法)都收敛成
    {"ok": False, "error": ...},好让 action_node 现有的失败反思/兜底逻辑照常工作。"""
    try:
        return asyncio.run(_acall(name, args))
    except Exception as e:
        return {"ok": False, "error": f"工具调用失败({name}):{e}"}
