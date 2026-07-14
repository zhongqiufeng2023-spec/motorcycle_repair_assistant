import json
from typing import Annotated, Literal
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_deepseek import ChatDeepSeek
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import ToolMessage

load_dotenv()

@tool 
def calculator(expression: str) -> str:
    """计算数学表达式,例如 '3*(4+5)'"""
    return str(eval(expression))

tools = [calculator]
tools_by_name = {t.name: t for t in tools}
llm = ChatDeepSeek(model="deepseek-chat").bind_tools(tools)


class State(TypedDict):
    messages: Annotated[list, add_messages]

def agent(state: State):
    return {"messages": [llm.invoke(state["messages"])]}

# def tool_node(state: State):
#     last_msg = state["messages"][-1]
#     results = []
#     for call in last_msg.tool_calls:
#         fn = tools_by_name[call["name"]]
#         output = fn.invoke(call["args"])
#         results.append(ToolMessage(
#             content = str(output),
#             tool_call_id = call["id"],
#         ))
#     return {"messages": results}

# def should_continue(state: State) -> Literal["tools", "__end__"]:
#     last_msg = state["messages"][-1]
#     if last_msg.tool_calls:
#         return "tools"
#     else:
#         return "__end__"
    
builder = StateGraph(State)
builder.add_node("agent", agent)
builder.add_node ("tools", ToolNode(tools))

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

graph = builder.compile(checkpointer=MemorySaver())

# print(graph.get_graph().draw_ascii())

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "顾客001"}}
    while True:
        input_question = input("\n请输入问题:")
        if input_question.lower() in ("exit","quit"):
            print ("退出聊天")
            break
        out = graph.invoke({"messages": [{"role": "user", "content": input_question}]}, config=config)
        print("AI:", out["messages"][-1].content)
    # question = "先算137*24,再把结果加上500,最后除以4,请一步一步做"
    # out = graph.invoke({"messages": [{"role": "user", "content": question}]}, config=config)
    # for m in out["messages"]:
    #     m.pretty_print()