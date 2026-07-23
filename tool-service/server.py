"""MCP 工具服务(独立进程,HTTP 常驻 :9000)。

薄壳/适配层:自己不写业务,只把 tools.py 的业务函数"摆到 MCP 协议上"。
- @mcp.tool 读函数签名 + docstring 自动生成 JSON Schema(docstring→工具描述,
  Annotated[..., Field(description=...)]→逐参数描述)。
- 客户端(agent)启动时 tools/list 动态发现,tools/call 远程执行。

跑法:  python tool-service/server.py     → 挂在 http://127.0.0.1:9000/mcp
依赖:  Spring Boot :8080(业务函数会去够它)。server 自身不连 Spring Boot,是 tools.py 连。
"""
from typing import Annotated
from pydantic import Field
from fastmcp import FastMCP
import tools   # 同目录的业务实现层(独立跑 server.py 时,脚本目录在 sys.path[0],直接 import)

mcp = FastMCP("moto-tools")


@mcp.tool
def query_order(
    order_id: Annotated[str, Field(description="订单号,纯数字字符串")],
) -> dict:
    """查询订单的状态和物流信息。需要订单号。"""
    return tools.query_order(order_id)


@mcp.tool
def book_service(
    date: Annotated[str, Field(description="预约时间,格式为 2026-07-18")],
    service_type: Annotated[str, Field(description="预约的服务类型")],
) -> dict:
    """查询可预约的日期,并帮助预约。需要日期和服务类型。"""
    return tools.book_service(date, service_type)


@mcp.tool
def request_refund(
    order_id: Annotated[str, Field(description="订单号,纯数字字符串")],
    reason: Annotated[str, Field(description="退款原因")],
    session_id: str = "",   # 系统注入,非 LLM 填写;客户端发给 LLM 前会剥掉此参数(见 app/mcp_client._SYSTEM_PARAMS)
) -> dict:
    """如果用户的话里已经包含退款原因(哪怕口语化,如不想要了买错了),直接采用,不要重复询问。
    为订单申请退款。仅支持已签收且签收不超过 7 天的订单;需订单号和退款原因。"""
    # 接缝已解:session_id 由 agent 侧注入、经 MCP 透传到这里 —— 退款开工单时记录发起会话,
    # 商家批复后好把结果推回那条对话。它 optional/默认空,故不进 required、也会被客户端从 LLM 视野剥掉。
    return tools.request_refund(order_id, reason, session_id or None)


if __name__ == "__main__":
    # transport="http":从 stdio(被客户端当子进程拉起)升级为独立 HTTP 常驻服务。
    # 这一行就是"本地工具"变"独立服务"的分界线——客户端从此靠 URL 连,不再需要本文件。
    mcp.run(transport="http", host="127.0.0.1", port=9000)
