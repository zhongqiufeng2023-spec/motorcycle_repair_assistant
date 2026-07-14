from typing import Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class S(TypedDict):
    number: int
    result: str

def entry(state: S):
    return {}                                   # 岔路口本身什么都不干

def route(state: S) -> Literal["even", "odd"]:  # 看一眼公文包,报出下一站的名字
    return "even" if state["number"] % 2 == 0 else "odd"

def even(state: S): return {"result": "偶数路"}
def odd(state: S):  return {"result": "奇数路"}

b = StateGraph(S)
b.add_node("entry", entry)
b.add_node("even", even) 
b.add_node("odd", odd)
b.add_edge(START, "entry")
b.add_conditional_edges("entry", route, {"even": "even", "odd": "odd"})
b.add_edge("even", END)
b.add_edge("odd", END)
g = b.compile()

print(g.invoke({"number": 7}))
print(g.invoke({"number": 42}))