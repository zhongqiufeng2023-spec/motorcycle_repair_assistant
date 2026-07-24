import os, sys, json, uuid
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.moto_manual import DOCS
from dotenv import load_dotenv
from openai import OpenAI
from typing import TypedDict, Optional
from app.query_processing import RouteDecision
from app.query_processing import detect_complaint, judge_complaint, check_faq, decide_route, decompose_query, generate_hyde, rewrite_with_history
from app.retriever import HybridRetriever
from app.graph_retriever import GraphRetriever
from langgraph.graph import StateGraph, END
from langsmith.wrappers import wrap_openai
from app import mcp_client
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from typing import Annotated


load_dotenv()
llm = wrap_openai(OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=os.getenv("BASE_URL")))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_chunks_path = os.path.join(BASE_DIR, "data", "manual_chunks.json")
# 手册是版权物、衍生语料与向量库均不入库。缺语料就明确报错并给出构建步骤,不静默降级
# (静默用 8 条 DOCS 硬撑会让人误以为有全量手册,更隐蔽)。
if not os.path.exists(_chunks_path):
    raise FileNotFoundError(
        "缺少语料 data/manual_chunks.json。使用前请先构建语料库:\n"
        "  1) 把手册 PDF 放进 data/raw_manuals/\n"
        "  2) python lab/lab_d10_1_ingest.py          # 切片:PDF → manual_chunks.json\n"
        "  3) python lab/lab_d10_2_build_corpus_db.py  # 向量化:切片 + 内置DOCS → Chroma 向量库\n"
    )
with open(_chunks_path, encoding="utf-8") as f:
    MANUAL_CHUNKS = [c["text"] for c in json.load(f)]
retriever = HybridRetriever(MANUAL_CHUNKS + DOCS, chroma_path = os.path.join(BASE_DIR,"data","chroma_db"))
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
    session_id: Optional[str]            # 入口塞进来=thread_id;开退款工单时注入给 request_refund
    user_id: Optional[str]               # 登录用户 id(FastAPI 验 JWT 后注入);开工单绑到谁、谁能查
    ticket_id: Optional[int]             # 本轮开出的退款工单号;透传给前端做结果轮询回推

def _generate(question: str, contexts: list[str], source: str = "维修手册") ->str:
    """给定问题和检索到的资料,生成最终回答"""
    context_text = "\n".join(f"- {c}" for c in contexts)
    prompt = f"""你是摩托车维修保养助手。下面是从【{source}】中检索到的资料,可能混有其他车型的条目。
    只依据与用户问题所指车型/主题相关的资料作答;无关车型的条目直接忽略,
    不要向用户提及资料的来源构成或你的筛选过程,直接给出干净的答案。
    如果资料中确实没有相关信息,就如实说"手册里没有查到相关信息",不要编造。

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
    d = decide_route(q, _history(state)[:-1])
    return {"decision": d.model_dump(), "route": f"{d.target}/{d.strategy or '-'}"}

def qa_node(state: AgentState) -> dict:
    strategy = state["decision"]["strategy"]
    q = rewrite_with_history(state["question"], _history(state))
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


# ask_user 不是业务工具,是"LLM 想问真人"的本地信号:无函数体,action_node 拦下来触发 interrupt。
# 它不能进 MCP(远程服务 pause 不了本进程的 graph、也够不着终端用户),所以 schema 留在 agent 侧。
ASK_USER_SCHEMA = {"type": "function", "function": {
    "name": "ask_user",
    "description": "当办理业务缺少必要信息(如订单号、预约日期)且无法从对话历史推断时,调用此工具向用户提问。不要用它闲聊,任何需要用户回话才能继续的情况(含确认猜测值)都必须走 ask_user。",
    "parameters": {"type": "object", "properties": {
        "question": {"type": "string", "description": "要问用户的话,一句话"},
        "options": {"type": "array", "items": {"type": "string"},
                    "description": "可选:给用户几个选项让他挑(如日期候选);没有就省略"},
    }, "required": ["question"]},
}}

# 工具清单 = MCP 动态发现的业务工具(tools/list) + 本地 ask_user。懒加载缓存:首个业务请求才连
# :9000 发现一次(agent 进程 import 不依赖工具服务在),之后复用。
_tool_schemas_cache = None
def _tool_schemas() -> list:
    global _tool_schemas_cache
    if _tool_schemas_cache is None:
        _tool_schemas_cache = mcp_client.get_tool_schemas() + [ASK_USER_SCHEMA]
    return _tool_schemas_cache


def action_node(state: AgentState) -> dict:
    q = state["question"]
    messages = [
        {"role": "system", "content": "你是摩托车店的业务办理助手。只能通过提供的工具办理业务,工具没覆盖的业务如实说明办不了。"
            "【关键机制】你无法直接用文字向用户提问或索取信息——唯一能向用户要信息的方式是调用 ask_user 工具。"
            "因此只要办理业务缺少必要信息(如订单号、预约日期)且无法从对话历史推断,你必须调用 ask_user 工具,绝不能用文字去问用户。"
            "只有在业务已办完、或确实办不了需要说明时,才用文字回复。"
            "工具返回失败时(如超过退款期限、订单不存在),必须如实、明确地告诉用户失败的具体原因和结论"
            "(例:'很抱歉,该订单已签收超过 7 天,超出无理由退款期,无法办理退款');"
            "严禁声称任何没有真实发生的动作——不要说'已登记工单''已转人工''专人会联系您',除非工具确实返回了工单号或转接信息。"
            "不要编造任何工具没有返回的信息。用简体中文回复。"},] + _history(state)
    fail_count = 0
    opened_ticket_id = None                 # 本轮若开了退款工单,记下单号,终局带给前端
    for _ in range(5):
        resp = llm.chat.completions.create(
            model = "deepseek-chat",messages = messages, tools = _tool_schemas(), temperature = 0
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return _final(msg.content, ticket_id=opened_ticket_id)
        messages.append(msg)

        for tc in msg.tool_calls:
            if tc.function.name == "ask_user":
                args = json.loads(tc.function.arguments)
                user_reply = interrupt({"type": "clarify",
                                        "question": args["question"],
                                        "options": args.get("options")})
                result = {"ok": True, "user_reply": user_reply}   # 用户的回答作为"工具结果"喂回
                messages.append({"role": "tool", "tool_call_id": tc.id,"content": json.dumps(result, ensure_ascii=False)})
                continue
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            if tc.function.name == "request_refund":
                args["session_id"] = state.get("session_id")   # 会话号不由 LLM 提供,节点注入,经 MCP 透传到工具服务
                args["user_id"] = state.get("user_id")         # 登录用户 id 同样节点注入、对 LLM 隐藏,经 MCP 透传绑到工单
            result = mcp_client.call(tc.function.name, args)    # 远程执行:tools/call → :9000 工具服务(桥接见 app/mcp_client)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)})  # 要点⑤
            if tc.function.name == "request_refund" and result.get("ok") and result.get("ticket_id"):
                opened_ticket_id = result["ticket_id"]   # 开单成功 → 记单号,前端据此轮询回推
            if not result.get("ok", True):
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

        # "订单123-45的火花塞我要退货,买错型号了",   # 高危 → 审核 → 你输 yes → 退款受理
        # "订单12345这个东西我不想要了,退货",       # 高危 → 审核 → 你输 no  → 驳回话术
        # "帮我查一下订单12-345到哪了",              # 对照:普通工具,不该触发审核
        # "帮我查一下订单22345到哪了",
        "Ninja 400 的机油容量是多少"
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