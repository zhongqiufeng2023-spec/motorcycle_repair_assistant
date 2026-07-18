import os, sys, json, uuid
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.moto_manual import DOCS
from dotenv import load_dotenv
from openai import OpenAI
from typing import TypedDict, Optional
from app.query_processing import RouteDecision
from app.query_processing import detect_complaint, judge_complaint, check_faq, decide_route, decompose_query, generate_hyde
from app.retriever import HybridRetriever
from app.graph_retriever import GraphRetriever
from langgraph.graph import StateGraph, END
from langsmith.wrappers import wrap_openai
from app.tools import TOOLS_SCHEMA, TOOL_REGISTRY, HIGH_RISK_TOOLS
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from typing import Annotated


load_dotenv()
llm = wrap_openai(OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=os.getenv("BASE_URL")))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
retriever = HybridRetriever(DOCS, chroma_path = os.path.join(BASE_DIR,"data","chroma_db"))
graphretriever = GraphRetriever()
_ROLE_MAP = {"human": "user", "ai": "assistant"}

class AgentState(TypedDict):
    messages: Annotated[list,add_messages]
    question: str                        # 用户问题(入口塞进来)
    decision: Optional[dict]    # supervisor 的决策
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

def _reflect_on_failure(tool_name: str, args: dict, error: str, question: str) -> str:
    """失败分析:给出修复建议(Reflexion 思想:语言反馈代替梯度)"""
    prompt = f"""工具调用失败,请分析原因并给出一句话建议。
    工具:{tool_name},参数:{json.dumps(args, ensure_ascii=False)}
    错误信息:{error}
    用户原始请求:{question}

    只回答一句话,三选一:
    - 若能修复(如参数格式不对):给出具体修正方式,例如"订单号可能含多余字符，比如：！,@,#,￥,%,……,&,*,（,）,—,—,+,-,=,？,‘,’,【,】,!,@,#,$,%,^,&,*,(,),_,+,-,=,?,,,.,;,',:,",应尝试 12345"
    - 若该换别的工具:说明换哪个
    - 若无法修复(如订单确实不存在、超出政策):回答"无法修复:"加原因,此时不应重试"""
    resp = llm.chat.completions.create(model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}], temperature=0)
    return resp.choices[0].message.content.strip()

def _chitchat_reply(question: str) -> str:
    """闲聊:不检索,直接回"""
    resp = llm.chat.completions.create(model="deepseek-chat",
    messages=[{"role": "user", "content": f"你是友好的摩托车客服,请简短回复:{question}"}])
    return resp.choices[0].message.content

def _complaint_reply(question: str) -> str:
    """投诉:先安抚,不辩解不甩参数,告知转人工"""
    resp = llm.chat.completions.create(model="deepseek-chat",
        messages=[{"role": "user", "content": f"""你是摩托车店的客服主管。用户正在投诉,请用真诚、简短的话安抚他。
    不要辩解,不要甩技术参数,表达歉意,并告知已为他登记工单,人工客服会尽快跟进。
    用简体中文回复,不要夹杂英文单词。

    用户的话:{question}"""}],
        temperature=0.3)   # 安抚话术要点人情味,不要死板
    return resp.choices[0].message.content

def _history(state: AgentState, n: int = 10) -> list[dict]:
    out = []
    for m in state["messages"][-n:]:
        role = _ROLE_MAP.get(m.type)
        if role is None:
            continue
        out.append({"role":role,"content":m.content})
    return out

def _final(answer: str, **extra) -> dict:
    """终局补丁:答案 + 记入对话史"""
    return {"answer": answer, "messages": [{"role": "assistant", "content": answer}], **extra}
        
def supervisor_node(state : AgentState) -> dict:
    q = state["question"]
    if detect_complaint(q) and judge_complaint(q):
        return {"decision": RouteDecision(target = "complaint").model_dump(),"route": "complaint"}
    faq = check_faq(q)
    if faq:
        return _final(faq,decision=RouteDecision(target="chitchat").model_dump(), route="FAQ")
    d = decide_route(q)
    return {"decision": d.model_dump(), "route": f"{d.target}/{d.strategy or '-'}"}

def qa_node(state: AgentState) -> dict:
    strategy = state["decision"]["strategy"]
    q = state["question"]
    if strategy == "knowledge":
        # 普通知识问题:直接混合检索 → 生成
        contexts = retriever.retrieve(q, top_k=3)
        return _final(_generate(q, contexts), contexts = contexts)
    if strategy == "compatibility":
        result = graphretriever.retrieve(q)
        if not result["ok"]:
            return _final("抱歉,查询配件图谱时出错了,换个说法再试试?", contexts = [], cypher= result.get("cypher"), error = result.get("error"))
        contexts = [str(row) for row in result["rows"]]
        source="配件兼容知识图谱的查询结果(每一行都是与用户问题匹配的兼容记录)"
        return _final( _generate(q, contexts,source = source), contexts = contexts, cypher = result["cypher"])

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
    return _final(_generate(q, all_contexts), contexts = all_contexts, sub_questions = sub_questions)


def action_node(state: AgentState) -> dict:
    q = state["question"]
    messages = [
        {"role": "system", "content": "你是摩托车店的业务办理助手。只能通过提供的工具办理业务,"
            "工具没覆盖的业务如实说明办不了。工具返回失败时,向用户解释原因;"
            "不要编造任何工具没有返回的信息。用简体中文回复。"},] + _history(state)
    fail_count = 0
    denied_tools = set()
    for _ in range(5):
        resp = llm.chat.completions.create(
            model = "deepseek-chat",messages = messages, tools = TOOLS_SCHEMA, temperature = 0
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return _final(msg.content)
        messages.append(msg)

        for tc in msg.tool_calls:
            fn = TOOL_REGISTRY.get(tc.function.name)
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args, fn ={},None
            if fn and tc.function.name in HIGH_RISK_TOOLS:
                if tc.function.name in denied_tools:
                     result = {"ok": False, "denied": True,
                              "error": "该操作已被商家驳回,不可重复申请,请如实告知用户"}
                else:
                    approval = interrupt(
                        {
                            "type":"approval_request",
                            "tool":tc.function.name,
                            "args":args,
                            "user_quesion":state["question"],
                        }
                    )
                    if approval == "yes":
                        result = fn(**args)
                    else:
                        denied_tools.add(tc.function.name)
                        result = {"ok": False, "error": "商家审核未通过,退款申请已驳回,将由人工客服跟进处理"}
            else:        
                result = fn(**args) if fn else {"ok": False, "error": f"未知工具 {tc.function.name}"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)})  # 要点⑤
            if not result.get("ok", True) and not result.get("denied"):
                fail_count += 1
                if fail_count>=3:
                    return _final("抱歉,该业务多次尝试仍未成功,已为您登记并转人工客服优先处理。", error = f"连续失败{fail_count}次,已转人工" )
                advice = _reflect_on_failure(tc.function.name, args, result.get("error",""),q)
                messages.append({"role": "user","content": f"【系统反思】工具 {tc.function.name} 调用失败。分析建议:{advice}。""若建议可执行,请修正后重试;若无法修复,请如实向用户说明,不要再重试。"})
    return _final("抱歉,这项业务办理遇到问题,已为您登记并转人工客服跟进。")


def chitchat_node(state: AgentState) -> dict:
    if state.get("answer"):   # FAQ 已经给过答案,别覆盖
        return {}
    return _final(_chitchat_reply(state["question"]))

def complaint_node(state: AgentState) -> dict:
    return _final( _complaint_reply(state["question"]))

def route_by_decision(state: AgentState) -> str:
    """条件边:读公文包,报下一站的名字"""
    return state["decision"]["target"]

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

app_graph = graph.compile(checkpointer=MemorySaver())


if __name__ == "__main__":
    tests = [
        # ---- 真投诉:必须走 complaint ----
        # "你们到底几点营业啊，我每次来都是关门的"
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

        # "你们到底几点营业啊，我每次来都是关门的",   # 你的边界用例(情绪×FAQ)
        # "帮我查一下订单12345到哪了",               # 单工具一轮
        # "我想约2026-07-18做个常规保养",             # 约满 → 看 LLM 怎么应对(重点)
        # "订单12347的刹车油我要退货",                # 超7天 → 应如实解释
        # "查一下订单12346到哪了,顺便约周日的保养",    # 复合 → 两轮两工具

        "订单123-45的火花塞我要退货,买错型号了",   # 高危 → 审核 → 你输 yes → 退款受理
        # "订单12345这个东西我不想要了,退货",       # 高危 → 审核 → 你输 no  → 驳回话术
        "帮我查一下订单12-345到哪了",              # 对照:普通工具,不该触发审核
        # "帮我查一下订单22345到哪了",
    ]
    RUN_ID = uuid.uuid4().hex[:8]  
    for i, q in enumerate(tests, 1):
        config = {"configurable": {"thread_id": f"{RUN_ID}-test-{i}"}}
        result = app_graph.invoke({"question": q, "messages":[{"role": "user", "content": q}],"contexts": [], "answer": "",
                                   "route": "", "decision": None}, config)
        while "__interrupt__" in result:
            print(f"对于问题：{q},需要请求人工审核\n⏸ 人工审核请求:{result['__interrupt__'][0].value}")
            human = input("你是商家审核员,批准吗?(yes/no): ")
            result = app_graph.invoke(Command(resume=human), config)
        print(f"{i}. 【{result['route']}】{q}")
        print(f"   {result['answer']}")