import os, sys, json, uuid, time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.moto_manual import DOCS
from dotenv import load_dotenv
from openai import OpenAI
from typing import TypedDict, Optional
from app.config import MODEL
from app.query_processing import RouteDecision, Intent
from app.query_processing import detect_complaint, judge_complaint, match_faq, decide_route, decompose_query, generate_hyde, rewrite_with_history
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

def _add_answers(old: Optional[list], new: Optional[list]) -> list:
    """answers 的 reducer:追加,但 new 传 None 表示【清空】。

    为什么不能直接用 operator.add:state 是按 thread 存的,累加器跨轮永不清零。
    第二轮进 merge 时 parts 里还躺着第一轮的答案 → len(parts)==1 不成立 → 白白走了
    _merge_reply,把上一轮的答案跟这一轮缝成一段(实测:multiturn-02#t2 的答案里
    含着 t1 的查询回执原文)。chitchat_node 的 `if state.get("answers")` 守卫同样受害:
    第二轮一进来就为真,那一轮直接不回答。
    累加器的生命周期必须是【一轮】,而不是【一个 thread】——由 merge_node 消费完就清。"""
    if new is None:
        return []
    return (old or []) + new

def _merge_error(old: Optional[str], new: Optional[str]) -> Optional[str]:
    """多意图并行时 qa 和 action 可能同一轮各自失败,两个写入者抢 error 会 InvalidUpdateError。
    给它一个 reducer:非空的拼起来,都空则 None。"""
    parts = [x for x in (old, new) if x]
    return " | ".join(parts) if parts else None

class AgentState(TypedDict):
    messages: Annotated[list,add_messages]
    question: str                        # 用户问题(入口塞进来,永远是完整原句)
    decision: Optional[dict]    # supervisor 的决策
    contexts: list[str]                  # 检索到的资料
    # 各分支往里【追加】自己那段答案(多意图时会有多条);reducer 让并行写入不打架。
    # 每条形如 {"target": "qa"/"action"/..., "text": "..."} —— 带上 target 是为了让
    # merge 认得出哪段是【业务回执】(不可改写),哪段是信息性回答(可润色)。
    answers: Annotated[list[dict], _add_answers]
    answer: str                          # 最终成品答案(只有 merge_node 写,一个字段一个写入者)
    route: str                           # 走过的路线(调试/评估用)
    cypher: Optional[str]           # 图检索溯源
    error: Annotated[Optional[str], _merge_error]   # 失败详情(别吞错误,你上次的教训)
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
    resp = llm.chat.completions.create(model=MODEL,
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
    resp = llm.chat.completions.create(model=MODEL,
        messages=[{"role": "user", "content": prompt}], temperature=0)
    return resp.choices[0].message.content.strip()

def _chitchat_reply(question: str, history: list[dict] | None = None) -> str:
    """闲聊 + 记忆型提问:不检索,带对话历史直接回。
    读账本是这一路的关键——用户问"我骑的是什么"这类问题,答案在历史里而不在手册里。"""
    msgs = [{"role": "system", "content":
             "你是友好的摩托车客服。可以依据对话历史回答用户问的、他自己先前说过的信息"
             "(如车型、订单号、偏好)。历史里没有的就如实说不知道,绝不编造。"
             "回复简短,用简体中文。"}]
    # _history 的末条就是本轮问题;没有历史时退化成只带当前问题
    msgs += history if history else [{"role": "user", "content": question}]
    resp = llm.chat.completions.create(model=MODEL, messages=msgs)
    return resp.choices[0].message.content

def _complaint_reply(question: str) -> str:
    """投诉:先安抚,不辩解不甩参数,告知转人工"""
    resp = llm.chat.completions.create(model=MODEL,
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

def _final(answer: str, target: str, **extra) -> dict:
    """分支终局补丁:把自己那段答案【追加】进 answers,连同 target 一起(merge 靠它区分回执与信息)。
    注意这里【不再记 messages】——多意图时两个分支各记一条,一轮问答会留下两条助手消息,
    历史就脏了。记账统一挪到 merge_node:谁产出【最终】答案谁记账。"""
    return {"answers": [{"target": target, "text": answer}], **extra}

def _route_str(d: RouteDecision) -> str:
    """路线字符串。单意图时必须与改造前【逐字节一致】,否则 43 条评估集的
    expected_route 精确比对会全红,而那跟新功能无关。多意图才用 + 连接。"""
    return "+".join(f"{i.target}/{i.strategy or '-'}" for i in d.intents)

def _my_question(state: AgentState, target: str) -> str:
    """取【本路】要处理的那半句。
    单意图时直接返回原句,不读 intent.question —— 这样即便 LLM 没听话、擅自精简了
    question,单意图路径也零扰动,评估基线稳如改造前。多意图才按 target 各取各的。"""
    intents = state["decision"]["intents"]
    # FAQ 部分命中时,交给路由的只是【剩下的子句】,原句里那半已由 FAQ 答过。
    # 此时"原句"不再是这一路该处理的东西,基准要换成 routed_question,否则分支会
    # 把 FAQ 已答的那半再答一遍(而它没有 FAQ 数据,只能说"没查到")。
    base = state["decision"].get("routed_question") or state["question"]
    if len(intents) <= 1:
        return base
    for i in intents:
        if i["target"] == target:
            return i["question"]
    return base

def supervisor_node(state : AgentState) -> dict:
    q = state["question"]
    if detect_complaint(q) and judge_complaint(q):
        d = RouteDecision(intents=[Intent(target="complaint", question=q)])
        return {"decision": d.model_dump(), "route": "complaint"}
    # FAQ 逐子句匹配,三种结果三种处置(判据与代价见 query_processing.match_faq)
    faq_hits, rest = match_faq(q)
    if faq_hits and not rest:
        # ① 全覆盖:短路,零 LLM 调用 —— FAQ 缓存的本职,成本分层的第一层
        d = RouteDecision(intents=[Intent(target="chitchat", question=q)])
        return _final("\n".join(faq_hits), "chitchat", decision=d.model_dump(), route="FAQ")

    # 只在【FAQ 部分命中】时才把问题换成 rest(摘掉已答子句);一条都没命中就原句照送。
    # 不能写成 `rest or q`:全不命中时 rest 是"所有子句用逗号重拼",标点被归一、礼貌前缀被剥,
    # 等于悄悄改了【全部非 FAQ 用例】送进路由的文本——那不在这次改动的意图里。
    d = decide_route(rest if faq_hits else q, _history(state)[:-1])
    dd = d.model_dump()
    patch = {"decision": dd, "route": _route_str(d)}
    if faq_hits:
        # ② 部分覆盖:FAQ 那段先入账当一路答案(merge 会和分支答案缝在一起),
        # 只把【未覆盖的子句】交给路由 —— 既不丢 FAQ 的答案,也不让分支去答它答不了的半句。
        dd["routed_question"] = rest
        patch["answers"] = [{"target": "chitchat", "text": "\n".join(faq_hits)}]
        patch["route"] = "FAQ+" + patch["route"]
    return patch
    # ③ 全不覆盖:照常走路由(patch 里没有 answers,route 就是纯路线串)

def qa_node(state: AgentState) -> dict:
    intents = state["decision"]["intents"]
    strategy = next((i["strategy"] for i in intents if i["target"] == "qa"), None)
    q = rewrite_with_history(_my_question(state, "qa"), _history(state))
    if strategy == "knowledge":
        # 普通知识问题:直接混合检索 → 生成
        contexts = retriever.retrieve(q, top_k=3)
        return _final(_generate(q, contexts), "qa", contexts = contexts)
    if strategy == "compatibility":
        result = graphretriever.retrieve(q)
        if not result["ok"]:
            return _final("抱歉,查询配件图谱时出错了,换个说法再试试?", "qa", contexts = [], cypher= result.get("cypher"), error = result.get("error"))
        contexts = [str(row) for row in result["rows"]]
        source="配件兼容知识图谱的查询结果(每一行都是与用户问题匹配的兼容记录)"
        return _final( _generate(q, contexts,source = source), "qa", contexts = contexts, cypher = result["cypher"])

    # 复杂问题:先改写,再检索
    # 策略1:先拆解成子问题
    sub_questions = decompose_query(q)
    # 策略2:每个子问题用HyDE生成诱饵,分别检索,汇总资料
    all_contexts = []
    for sub_q in sub_questions:
        t0 = time.perf_counter()
        hyde = generate_hyde(sub_q)
        t1 = time.perf_counter()
        ctxs = retriever.retrieve(hyde, top_k=2)
        t2 = time.perf_counter()
        print(f"[{sub_q[:20]}] hyde={t1-t0:.2f}s retrieve={t2-t1:.2f}s")
        all_contexts.extend(ctxs)
    # 去重(不同子问题可能检索到同一条)
    all_contexts = list(dict.fromkeys(all_contexts))
    return _final(_generate(q, all_contexts), "qa", contexts = all_contexts, sub_questions = sub_questions)


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
    q = _my_question(state, "action")
    hist = _history(state)
    # 多意图时,把历史末条(=本轮完整原句)换成【属于 action 的那半句】。
    # 不换的话 LLM 会连带回应"问火花塞"那半 —— 而它手里没有手册工具,只能编。
    # 单意图时 q 恒等于原句,这里是恒等操作,对 43 条基线零扰动。
    if hist and hist[-1]["role"] == "user":
        hist[-1] = {"role": "user", "content": q}
    messages = [
        {"role": "system", "content": "你是摩托车店的业务办理助手。只能通过提供的工具办理业务,工具没覆盖的业务如实说明办不了。"
            "【关键机制】你无法直接用文字向用户提问或索取信息——唯一能向用户要信息的方式是调用 ask_user 工具。"
            "因此只要办理业务缺少必要信息(如订单号、预约日期)且无法从对话历史推断,你必须调用 ask_user 工具,绝不能用文字去问用户。"
            "只有在业务已办完、或确实办不了需要说明时,才用文字回复。"
            "工具返回失败时(如超过退款期限、订单不存在),必须如实、明确地告诉用户失败的具体原因和结论"
            "(例:'很抱歉,该订单已签收超过 7 天,超出无理由退款期,无法办理退款');"
            "严禁声称任何没有真实发生的动作——不要说'已登记工单''已转人工''专人会联系您',除非工具确实返回了工单号或转接信息。"
            "不要编造任何工具没有返回的信息。用简体中文回复。"},] + hist
    fail_count = 0
    opened_ticket_id = None                 # 本轮若开了退款工单,记下单号,终局带给前端
    for _ in range(5):
        resp = llm.chat.completions.create(
            model = MODEL,messages = messages, tools = _tool_schemas(), temperature = 0
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return _final(msg.content, "action", ticket_id=opened_ticket_id)
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
                # 会话号/用户 id 不由 LLM 提供,节点注入,经 MCP 透传到工具服务。
                # 必须兜成空串:MCP schema 声明的是 str,直接塞 None 会被 Pydantic 拒掉
                # (整个调用还没发出就失败),导致无 session/user 的调用路径退款全挂。
                args["session_id"] = state.get("session_id") or ""
                args["user_id"] = state.get("user_id") or ""
            result = mcp_client.call(tc.function.name, args)    # 远程执行:tools/call → :9000 工具服务(桥接见 app/mcp_client)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)})  # 要点⑤
            if tc.function.name == "request_refund" and result.get("ok") and result.get("ticket_id"):
                opened_ticket_id = result["ticket_id"]   # 开单成功 → 记单号,前端据此轮询回推
            if not result.get("ok", True):
                fail_count += 1
                if fail_count>=3:
                    # 带上 ticket_id:复合请求里退款可能已开单成功、后一个工具才连败转人工。
                    # 不带出去 = 一张真实存在的工单前端不知道去轮询,商家批复结果永远推不回来。
                    return _final("抱歉,该业务多次尝试仍未成功,已为您登记并转人工客服优先处理。", "action",
                                  ticket_id=opened_ticket_id, error = f"连续失败{fail_count}次,已转人工" )
                advice = _reflect_on_failure(tc.function.name, args, result.get("error",""),q)
                messages.append({"role": "user","content": f"【系统反思】工具 {tc.function.name} 调用失败。分析建议:{advice}。""若建议可执行,请修正后重试;若无法修复,请如实向用户说明,不要再重试。"})
    return _final("抱歉,这项业务办理遇到问题,已为您登记并转人工客服跟进。", "action", ticket_id=opened_ticket_id)


def chitchat_node(state: AgentState) -> dict:
    # 守卫:只有 FAQ【全覆盖短路】时 supervisor 已经把答案给全了,这一路不该再答。
    # 判据必须是 route=="FAQ" 而不是"answers 非空"——FAQ【部分覆盖】时 answers 也非空,
    # 但那一段答的是另外的子句,本路仍有自己的半句要答,拿 answers 当守卫会让它闭嘴。
    if state.get("route") == "FAQ":
        return {}
    return _final(_chitchat_reply(_my_question(state, "chitchat"), _history(state)), "chitchat")

def complaint_node(state: AgentState) -> dict:
    return _final(_complaint_reply(state["question"]), "complaint")


def _merge_reply(parts: list[dict]) -> str:
    """把多路答案缝成一段话。
    铁律:【业务回执不可改写】—— qa 那半是只读信息,润色无所谓;action 那半是回执,
    事情已经真实发生了(工单开了、槽位占了)。让 LLM 重写回执,用户看到的就可能
    和系统实际做的对不上。所以回执原文保留,只让它润色信息段 + 写衔接。
    (结构化事实如 ticket_id 走 State 字段透传,一个字都不进这里。)"""
    receipts = [p["text"] for p in parts if p["target"] == "action"]
    infos    = [p["text"] for p in parts if p["target"] != "action"]
    prompt = f"""把下面两部分内容合并成一段自然、连贯的客服回复,用简体中文。

    【必须原样保留、一个字都不许改写的业务办理回执】
    {chr(10).join(receipts) if receipts else "(无)"}

    【可以润色改写的信息性回答】
    {chr(10).join(infos) if infos else "(无)"}

    要求:
    - 回执部分原样输出,不得改写、不得省略、不得增补任何未发生的动作。
    - 信息部分可以精简润色,去掉重复的客套。
    - 两部分之间加自然的过渡,合成一段完整回复;不要用小标题、不要分点罗列。
    - 不要提及"两部分""系统""合并"之类的元信息。"""
    resp = llm.chat.completions.create(model=MODEL,
        messages=[{"role": "user", "content": prompt}], temperature=0)
    return resp.choices[0].message.content


def merge_node(state: AgentState) -> dict:
    """汇总节点:所有分支的唯一出口。也是【本轮对话记账的唯一地点】。
    单路时直接透传,不调 LLM —— 否则 43 条单意图用例每条白白多花一次调用 + 两秒延迟。"""
    parts = state.get("answers") or []
    if not parts:
        final = "抱歉,没能处理您的问题,请换个说法再试试。"
    elif len(parts) == 1:
        final = parts[0]["text"]
    else:
        final = _merge_reply(parts)
    # answers=None 清空累加器:它只服务【这一轮】的扇入,消费完就还原,不许带进下一轮。
    return {"answer": final, "messages": [{"role": "assistant", "content": final}],
            "answers": None}


def route_by_decision(state: AgentState) -> list[str]:
    """条件边:读公文包,报下一站的名字。
    返回【列表】= 同一超步内并行激活多个节点(多意图时 qa 和 action 一起跑)。
    去重是防御性的:按 prompt 判据同一处理单元应合并成一个 intent,真出现重复
    target 也不该让同一个节点被激活两次。"""
    seen, out = set(), []
    for i in state["decision"]["intents"]:
        if i["target"] not in seen:
            seen.add(i["target"])
            out.append(i["target"])
    return out

graph = StateGraph(AgentState)
graph.add_node("supervisor", supervisor_node)
graph.add_node("qa",qa_node)
graph.add_node("action", action_node)
graph.add_node("chitchat", chitchat_node)
graph.add_node("complaint", complaint_node)
graph.add_node("merge", merge_node)

graph.set_entry_point("supervisor")
# 条件边返回【列表】→ 多意图时同一超步并行激活多个分支(扇出)
graph.add_conditional_edges("supervisor", route_by_decision,
    {"qa": "qa", "action": "action", "chitchat": "chitchat", "complaint": "complaint"})
# 四路统一汇入 merge(扇入),再到 END。merge 是答案与记账的唯一出口。
for n in ["qa", "action", "chitchat", "complaint"]:
    graph.add_edge(n, "merge")
graph.add_edge("merge", END)

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