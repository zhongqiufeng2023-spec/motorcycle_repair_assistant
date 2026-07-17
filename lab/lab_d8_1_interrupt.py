from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver

class S(TypedDict):
    amount: int
    result: str

def refund_node(state: S) -> dict:
    print(">>节点开始执行")
    decision = interrupt({"ask": f"申请退款{state["amount"]}元，批准吗？(yes/no)"})
    if decision == "yes":
        return {"result":"退款已执行"}
    return {"result":"已拒绝，转人工"}

builder = StateGraph(S)
builder.add_node("refund", refund_node)
builder.set_entry_point("refund")
builder.add_edge("refund", END)
graph = builder.compile(checkpointer=MemorySaver()) 

config = {"configurable": {"thread_id": "demo-1"}}
r1 = graph.invoke({"amount": 200, "result": ""}, config)
print("第一次 invoke 返回:", r1)

human = input("你现在是店里的审核员,批不批?(yes/no): ")
r2 = graph.invoke(Command(resume=human), config)      # ← 同一个 config!
print("恢复后:", r2)

    