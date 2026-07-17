import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.moto_manual import DOCS
from dotenv import load_dotenv
from openai import OpenAI
from typing import TypedDict, Optional
from app.query_processing import RouteDecision
from app.query_processing import detect_complaint, judge_complaint, check_faq, decide_route, decompose_query, generate_hyde
from retriever import HybridRetriever
from graph_retriever import GraphRetriever
from langgraph.graph import StateGraph, END
from langsmith.wrappers import wrap_openai

load_dotenv()
llm = wrap_openai(OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=os.getenv("BASE_URL")))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
retriever = HybridRetriever(DOCS, chroma_path = os.path.join(BASE_DIR,"data","chroma_db"))
graphretriever = GraphRetriever()

class AgentState(TypedDict):
    question: str                        # 用户问题(入口塞进来)
    decision: Optional[RouteDecision]    # supervisor 的决策
    contexts: list[str]                  # 检索到的资料
    answer: str                          # 最终答案
    route: str                           # 走过的路线(调试/评估用)
    cypher: Optional[str]           # 图检索溯源
    error: Optional[str]            # 失败详情(别吞错误,你上次的教训)
    sub_questions: Optional[list[str]]

def _generate(question: str, contexts: list[str], source: str = "维修手册") ->str:
    """给定问题和检索到的资料,生成最终回答"""
    context_text = "\n".join(f"- {c}" for c in contexts)
    prompt = f"""你是Ninja 400的汽修助手。下面是从【{source}】中查到的资料，请严格根据下面的资料回答用户问题。
如果资料中没有相关信息,就如实说"手册里没有查到相关信息",不要编造。

【参考资料】
{context_text}

【用户问题】
{question}
"""
    resp = llm.chat.completions.create(model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content

def _chitchat_reply(question: str) -> str:
    """闲聊:不检索,直接回"""
    resp = llm.chat.completions.create(model="deepseek-chat",
    messages=[{"role": "user", "content": f"你是友好的摩托车客服,请简短回复:{question}"}])
    return resp.choices[0].message.content

def _complaint_reply(question: str) -> str:
    """投诉:先安抚,不辩解不甩参数,告知转人工"""
    resp = llm.chat.completions.create(model="deepseek-chat",
        messages=[{"role": "user", "content": f"""你是摩托车店的客服主管。用户正在投诉,请用真诚、简短的话安抚他。
    不要辩解,不要甩技术参数,表达歉意,并告知已为他转接人工客服跟进。
    用简体中文回复,不要夹杂英文单词。

    用户的话:{question}"""}],
        temperature=0.3)   # 安抚话术要点人情味,不要死板
    return resp.choices[0].message.content

def supervisor_node(state : AgentState) -> dict:
    q = state["question"]
    if detect_complaint(q) and judge_complaint(q):
        return {"decision": RouteDecision(target = "complaint"),"route": "complaint"}
    faq = check_faq(q)
    if faq:
        return {"decision": RouteDecision(target="chitchat"),"answer": faq, "route":"FAQ"}
    d = decide_route(q)
    return {"decision": d, "route": f"{d.target}/{d.strategy or '-'}"}

def qa_node(state: AgentState) -> dict:
    strategy = state["decision"].strategy
    q = state["question"]
    if strategy == "knowledge":
        # 普通知识问题:直接混合检索 → 生成
        contexts = retriever.retrieve(q, top_k=3)
        return {"answer": _generate(q, contexts), "contexts": contexts}
    if strategy == "compatibility":
        result = graphretriever.retrieve(q)
        if not result["ok"]:
            return {
                    "answer": "抱歉,查询配件图谱时出错了,换个说法再试试?",
                    "contexts": [], "cypher": result.get("cypher"),
                    "error": result.get("error")}
        contexts = [str(row) for row in result["rows"]]
        source="配件兼容知识图谱的查询结果(每一行都是与用户问题匹配的兼容记录)"
        
        return {"answer": _generate(q, contexts,source = source),"contexts": contexts, "cypher": result["cypher"]}

    # 复杂问题:先改写,再检索
    # 策略1:先拆解成子问题
    sub_questions = decompose_query(q)
    # 策略2:每个子问题用HyDE生成诱饵,分别检索,汇总资料
    all_contexts = []
    for sub_q in sub_questions:
        hyde = generate_hyde(sub_q)
        ctxs = retriever.retrieve(hyde, top_k=2)   # 每个子问题少取几条,避免总量爆炸
        all_contexts.extend(ctxs)
    # 去重(不同子问题可能检索到同一条)
    all_contexts = list(dict.fromkeys(all_contexts))
    return {"answer": _generate(q, all_contexts), "contexts": all_contexts, "sub_questions": sub_questions}

def action_node(state: AgentState) -> dict:
    # D8 才真做,现在放个诚实的占位
    return {"answer": "您的业务请求已登记,人工客服将尽快与您联系(业务办理功能建设中)。"}

def chitchat_node(state: AgentState) -> dict:
    if state.get("answer"):   # FAQ 已经给过答案,别覆盖
        return {}
    return {"answer": _chitchat_reply(state["question"])}

def complaint_node(state: AgentState) -> dict:
    return {"answer": _complaint_reply(state["question"])}

def route_by_decision(state: AgentState) -> str:
    """条件边:读公文包,报下一站的名字"""
    return state["decision"].target

graph = StateGraph(AgentState)
graph.add_node("supervisor", supervisor_node)
graph.add_node("qa",qa_node)
graph.add_node("action", action_node)
graph.add_node("chitchat", chitchat_node)
graph.add_node("complaint", complaint_node)

graph.set_entry_point("supervisor")
graph.add_conditional_edges("supervisor", route_by_decision,
    {"qa": "qa", "action": "action", "chitchat": "chitchat", "complaint": "complaint"})
for n in ["qa", "action", "chitchat", "complaint"]:
    graph.add_edge(n, END)

app_graph = graph.compile()


if __name__ == "__main__":
    tests = [
        # ---- 真投诉:必须走 complaint ----
        "你们到底几点营业啊，我每次来都是关门的"
        # "你们这店太坑了,来回折腾三趟,退钱!",
        # "客服态度也太差了吧,一直推脱",
        # "在你们家修车三次都没修好,太失望了",
        # # ---- 关键对照:负面词一堆,但不是投诉,必须走 diagnosis ----
        # "我的刹车失灵了,太危险了",
        # "车子异响,烦死了",
        # # ---- 防回归:确认没把老功能搞坏 ----
        # "火花塞的电极间隙是多少",              # knowledge
        # "我2020年的Ninja 400能用什么火花塞",   # compatibility
        # "客服态度好了,一直很负责任",          # 夸奖,不是投诉

        # "我想知道你们的营业时间",              # FAQ
        # "帮我查一下订单12345到哪了",           # action(占位回复)
    ]

    for i, q in enumerate(tests,1):
        result = app_graph.invoke({"question": q, "contexts": [], "answer": "", "route": "", "decision": None})
        print(f"{i}. 【{result['route']}】{q}")
        print(f"   {result['answer'][:80]}...")