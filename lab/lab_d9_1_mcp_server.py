import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastmcp import FastMCP
from app import tools as t

mcp = FastMCP("moto-tools")

@mcp.tool
def query_order(order_id: str) -> dict:
    """查询订单状态。订单号应为纯数字。"""
    return t.query_order(order_id)
@mcp.tool
def book_service(date: str, service_type: str) -> dict:
    """查询可预约的日期，并帮助预约。需要日期和服务类型"""
    return t.book_service(date, service_type)

@mcp.tool
def request_refund(order_id: str, reason: str) -> dict:
    """如果用户的话里已经包含退款原因(哪怕口语化,如不想要了买错了),直接采用,不要重复询问。为订单申请退款。仅支持已签收且签收不超过 7 天的订单;需订单号和退款原因。"""
    return t.request_refund(order_id, reason)

if __name__ == "__main__":
    mcp.run()   # 默认 stdio:等着被客户端当子进程拉起