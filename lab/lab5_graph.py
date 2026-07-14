from typing import Annotated
from typing_extensions import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_deepseek import ChatDeepSeek

load_dotenv()
llm = ChatDeepSeek(model="deepseek-chat")

class State(TypedDict):
    messages: Annotated[list, add_messages]
    
def chatbot(state: State):
    return {"messages": [llm.invoke(state["messages"])]}

builder = StateGraph(State)
builder.add_node("chatbot", chatbot)     # 注册站点
builder.add_edge(START, "chatbot")       # 入口 → 站点
builder.add_edge("chatbot", END)         # 站点 → 出口
graph = builder.compile()

out = graph.invoke({"messages": [{"role": "user", "content": "一句话介绍Ninja 400"}]})
print(out["messages"][-1].content)