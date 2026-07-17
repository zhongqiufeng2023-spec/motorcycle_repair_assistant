# ==================== mock 数据(充当"业务数据库") ====================
MOCK_ORDERS = {
    "12345": {"item": "NGK CPR8EA-9 火花塞", "status": "已签收", "days_since_delivery": 3},
    "12346": {"item": "DID 520 链条", "status": "配送中", "days_since_delivery": None},
    "12347": {"item": "DOT4 刹车油", "status": "已签收", "days_since_delivery": 15},  # ← 故意超7天,退款会被拒
}
MOCK_SLOTS = {"2026-07-18": "已满", "2026-07-19": "可约", "2026-07-20": "可约"}

def query_order(order_id: str) -> dict:
    order = MOCK_ORDERS.get(order_id)
    if order is None:
        return {"ok": False, "error": f"订单 {order_id} 不存在。注意:订单号应为纯数字,若含有连字符、空格等符号,请去除后重试"}
    return {"ok": True, **order}

def book_service(date: str, service_type:str) -> dict:
    book_state = MOCK_SLOTS.get(date)
    if book_state:
        if book_state == "已满":
            available = [d for d, s in MOCK_SLOTS.items() if s == "可约"]
            return {"ok": False, "error": f"{date} 已约满,可约日期:{available}"}
        if book_state == "可约":
            return {"ok": True, "date": date, "service_type": service_type,
        "message": f"已为您预约 {date} 的{service_type}服务"}
        
    return {"ok": False, "error": f"预约时间{date}不存在"}

def request_refund(order_id: str, reason: str) -> dict:
    order = MOCK_ORDERS.get(order_id)
    if order is None:
        return {"ok": False, "error": f"订单 {order_id} 不存在,请核对订单号"}
    days = order["days_since_delivery"]
    if days is None:
        return {"ok": False, "error": f"订单 {order_id} 尚未签收,暂不能申请退款"}
    if days > 7:
        return {"ok": False, "error": f"订单 {order_id} 已签收 {days} 天,超出 7 天无理由退换期"}
    return {"ok": True,"order": order, "reason": reason, "message": "退款将在 3-5 个工作日原路退回"}

TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "query_order",
        "description": "查询订单的状态和物流信息。需要订单号。",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "订单号,纯数字字符串"}},
            "required": ["order_id"],
        },
    }},
    {"type": "function", "function": {
        "name": "book_service",
        "description": "查询可预约的日期，并帮助预约。需要日期和服务类型",
        "parameters": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "预约时间，格式为2026-07-18"}, "service_type": {"type": "string", "description": "预约的服务类型"}},
            
            "required": ["date","service_type"],
        },
    }},
    {"type": "function", "function": {
        "name": "request_refund",
        "description": "如果用户的话里已经包含退款原因(哪怕口语化,如不想要了买错了),直接采用,不要重复询问。为订单申请退款。仅支持已签收且签收不超过 7 天的订单;需订单号和退款原因。",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "订单号,纯数字字符串"}, "reason": {"type": "string", "description": "退款原因"},},
            "required": ["order_id","reason"],
        },
    }},
   ]

TOOL_REGISTRY = {"query_order": query_order, "book_service": book_service, "request_refund": request_refund}
HIGH_RISK_TOOLS = {"request_refund"}    

if __name__ == "__main__":
    print(query_order("12345"))          # 成功
    print(query_order("99999"))          # 失败:不存在
    print(book_service("2026-07-19", "常规保养"))   # 成功
    print(book_service("2026-07-18", "常规保养"))   # 失败:已满
    print(request_refund("12345", "买错型号"))      # 成功(3天内)
    print(request_refund("12347", "不想要了"))      # 失败:超7天
    print(request_refund("12346", "不想要了"))      # 失败:未签收 ← 专测 None 分支