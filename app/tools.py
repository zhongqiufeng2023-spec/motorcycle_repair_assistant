import os, json, urllib.request, urllib.error

# 业务系统(Spring Boot)地址;退款工单开在这里。可用环境变量覆盖。
BUSINESS_API = os.getenv("BUSINESS_API_URL", "http://localhost:8080")

# ==================== 业务系统访问(订单/槽位/工单都在 Spring Boot) ====================
# 订单/槽位数据已从 Python 内存字典迁到业务系统(唯一权威),这里只当调用方。

def _biz_get(path: str):
    """GET 业务系统。返回 (ok, http_code, payload);连不上时 code=None。"""
    try:
        with urllib.request.urlopen(f"{BUSINESS_API}{path}", timeout=5) as r:
            return True, r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:               # 4xx/5xx:body 里通常有 {"error":...}
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {}
        return False, e.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, None, {"error": str(e)}

def query_order(order_id: str) -> dict:
    ok, code, data = _biz_get(f"/orders/{order_id}")
    if ok:
        # 字段名对齐老契约(item/status/days_since_delivery),LLM 侧无感
        return {"ok": True, "item": data["itemName"], "status": data["status"],
                "days_since_delivery": data["daysSinceDelivery"]}
    if code == 404:
        return {"ok": False, "error": f"订单 {order_id} 不存在。注意:订单号应为纯数字,若含有连字符、空格等符号,请去除后重试"}
    return {"ok": False, "error": f"查询订单失败,业务系统暂时不可用({data.get('error')})"}

def book_service(date: str, service_type: str) -> dict:
    ok, code, slot = _biz_get(f"/slots/{date}")
    if not ok:
        if code == 404:
            return {"ok": False, "error": f"预约时间 {date} 不在排班表,请换个日期"}
        return {"ok": False, "error": f"预约系统暂时不可用({slot.get('error')})"}
    if slot["available"]:
        return {"ok": True, "date": date, "service_type": service_type,
                "message": f"已为您预约 {date} 的{service_type}服务"}
    # 已满 → 列出可约日期给用户挑
    ok2, _, avail = _biz_get("/slots?availableOnly=true")
    dates = [s["slotDate"] for s in avail] if ok2 else []
    return {"ok": False, "error": f"{date} 已约满,可约日期:{dates}"}

def request_refund(order_id: str, reason: str, session_id: str = None) -> dict:
    """预检退款资格(政策仍在 LLM 视野内=省审批人注意力),通过则【开工单】,不再当场退款、不再 interrupt。
    session_id 由 action_node 注入(记录发起会话,商家批复后好把结果推回这条对话)。"""
    ok, code, order = _biz_get(f"/orders/{order_id}")
    if not ok:
        if code == 404:
            return {"ok": False, "error": f"订单 {order_id} 不存在,请核对订单号"}
        return {"ok": False, "error": f"业务系统暂时不可用,请稍后再试({order.get('error')})"}
    days = order["daysSinceDelivery"]
    if days is None:
        return {"ok": False, "error": f"订单 {order_id} 尚未签收,暂不能申请退款"}
    if days > 7:
        return {"ok": False, "error": f"订单 {order_id} 已签收 {days} 天,超出 7 天无理由退换期"}
    # 预检通过 → 调业务系统开退款工单(PENDING),对话不挂起、立刻返回单号
    try:
        payload = json.dumps({"orderId": order_id, "sessionId": session_id or "",
                              "reason": reason, "itemName": order["itemName"]}).encode("utf-8")
        req = urllib.request.Request(f"{BUSINESS_API}/tickets", data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            ticket = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "error": f"工单系统暂时不可用,请稍后再试({e})"}
    return {"ok": True, "ticket_id": ticket["id"],
            "message": f"已为您提交退款工单(单号 {ticket['id']}),商家审核后会通知您,请勿重复提交"}

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

    {"type": "function", "function": {
        "name": "ask_user",
        "description": "当办理业务缺少必要信息(如订单号、预约日期)且无法从对话历史推断时,调用此工具向用户提问。不要用它闲聊,任何需要用户回话才能继续的情况(含确认猜测值)都必须走 ask_use。",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "要问用户的话,一句话"},
                "options": {"type": "array", "items": {"type": "string"},
                            "description": "可选:给用户几个选项让他挑(如日期候选);没有就省略"},
            },
            "required": ["question"],
        },
    }}
   ]

TOOL_REGISTRY = {"query_order": query_order, "book_service": book_service, "request_refund": request_refund}

if __name__ == "__main__":
    print(query_order("12345"))          # 成功
    print(query_order("99999"))          # 失败:不存在
    print(book_service("2026-07-19", "常规保养"))   # 成功
    print(book_service("2026-07-18", "常规保养"))   # 失败:已满
    print(request_refund("12345", "买错型号"))      # 成功(3天内)
    print(request_refund("12347", "不想要了"))      # 失败:超7天
    print(request_refund("12346", "不想要了"))      # 失败:未签收 ← 专测 None 分支