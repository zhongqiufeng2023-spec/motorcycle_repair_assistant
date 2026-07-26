import os, sys, json, re
# 直跑(python app/query_processing.py)时项目根不在 sys.path,下面的 app.config 会 import 失败。
# 补一行引导,让「直跑」和「作为包被 import」两种启动方式都成立(坑 7)。
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from openai import OpenAI
from FlagEmbedding import BGEM3FlagModel
import numpy as np
from typing import Literal, Optional
from pydantic import BaseModel, ValidationError
from langsmith.wrappers import wrap_openai
from app.config import MODEL

load_dotenv()
llm = wrap_openai(OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url = os.getenv("BASE_URL")))
# FAQ匹配要用向量,复用BGE-M3
_embed_model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
# ==================== FAQ 匹配 ====================
FAQ_DATA = {
        "本店营业时间为周一至周六 9:00-18:00,周日休息。": [
        "你们几点营业", "营业时间是什么时候", "周末开门吗", "礼拜天上班吗"
    ],
    # "配件类商品未拆封状态下 7 天内可退货,请保留购买凭证。": [
    #     "怎么退货", "退货政策是什么", "买的东西能退吗"
    # ],
    "客服热线:400-xxx-xxxx。": [
        "客服电话多少", "怎么联系你们", "有没有联系方式"
    ],
}
COMPLAINT_EXAMPLES = [
    "你们这店太坑了,来回折腾三趟,退钱!",
    "客服态度太差了,一直推脱责任",
    "买的配件质量太差,装上就坏了",
    "修了三次还没修好,你们到底行不行",
    "再不解决我就去消协投诉你们",
    "我要投诉,这服务太让人失望了",
]

_faq_questions, _faq_answers = [], []
for _ans, _qs in FAQ_DATA.items():
    for q in _qs:
        _faq_questions.append(q)
        _faq_answers.append(_ans)
_faq_vectors = _embed_model.encode(_faq_questions)['dense_vecs']
_complaint_vectors = _embed_model.encode(COMPLAINT_EXAMPLES)['dense_vecs']

def _max_similarity(q_vec, vectors) -> tuple[float, int]:
    """返回最大余弦相似度及其索引"""
    sims = [np.dot(q_vec, v) / (np.linalg.norm(q_vec) * np.linalg.norm(v)) for v in vectors]
    best = int(np.argmax(sims))
    return sims[best], best

def detect_complaint(question: str, threshold: float = 0.65) -> bool:
    q_vec = _embed_model.encode([question])['dense_vecs'][0]
    sim, _ = _max_similarity(q_vec, _complaint_vectors)
    return sim >= threshold

def judge_complaint(question: str) -> bool:
    """第二层:LLM 判断是否为针对本店的投诉(贵但准,只处理第一层筛出的少数)"""
    prompt = f"""你是摩托车售后客服系统的投诉识别器。判断用户这句话是不是【针对本店/本公司的投诉或不满】。
    只回答 yes 或 no,不要解释。

    判断标准:
    - yes(是投诉):明确对本店的服务、态度、质量、处理效率表达不满或愤怒。
    例:"客服态度太差了,一直推脱" / "修了三次还没修好" / "你们太坑了,退钱!"
    - no(不是投诉):
    · 只是要求办理业务(退款/退货/查订单/预约保养),即使语气不耐烦。例:"我要退款" / "这个不想要了,退款" / "订单12347退货"
    · 只是描述车辆故障,哪怕用词很负面。例:"我的刹车失灵了,太危险了" / "车子异响,烦死了"
    · 表达感谢或称赞。例:"你们服务真不错"
    · 普通技术咨询。例:"机油多久换一次"
    关键区分:单纯要办退款/退货=【业务请求 no】;只有同时痛斥本店服务/人员才算投诉 yes。

    用户的话:{question}
    回答(yes/no):"""
    resp = llm.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    # 兜底:LLM 没老实回 yes/no 就当作"不是投诉",走正常流程(至少能给用户答案)
    return resp.choices[0].message.content.strip().lower().startswith("yes")

# ==================== 路由决策 ====================
class Intent(BaseModel):
    """一个处理单元要办的一件事。
    question 是【这一路要处理的那半句】——单意图时就是完整原句,多意图时是切开的一半。
    切开是必需的:若两路都收到整句"问火花塞+约保养",qa 生成时会看到"帮我预约"
    而尴尬地一并回应,产出一个假装办了预约的答案。"""
    target: Literal["qa", "action", "chitchat", "complaint"]
    strategy: Optional[Literal["knowledge", "compatibility", "diagnosis"]] = None
    question: str

class RouteDecision(BaseModel):
    """一次路由的完整决策。intents 通常只有一个;只有当用户提出的多件事
    【分属不同处理单元】时才会有多个(如"查火花塞参数"+"约保养")。"""
    intents: list[Intent]

def decide_route(question: str, history: list[dict] | None = None) -> RouteDecision:
    # 有历史才注入:让路由在多轮里读懂"是/12345/日期"这类只在上文成立的裸回复;
    # 无历史(单轮)时 history_block 为空,prompt 与原来逐字一致,不动 46 条评估基线。
    history_block = ""
    if history:
        lines = "\n".join(
            f"    {'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
            for m in history
        )
        history_block = f"""
    【最近对话历史】(仅供理解上下文;判断路由请以下面的【用户问题】那一句为准)
{lines}

    结合历史的两条判据:
    - 以【用户问题】那一句为主判断路由;历史只用于消解指代和省略,别被旧话题带偏。
      例:上文在办退款,当前【用户问题】却问"机油多久换一次",应判 qa/knowledge,不是 action。
    - 若【用户问题】是对助手上一句追问的简短回答("是/对/嗯"、一串纯数字、一个日期),
      归到那句追问所属的处理单元——上文助手在办业务(查单/预约/退款)就判 action。
"""
    prompt = f"""你是摩托车售后客服系统的路由器。判断用户问题该交给哪个处理单元。
    以 JSON 返回,不要解释,不要 markdown 代码块。

    返回格式(intents 是数组,绝大多数情况只含 1 个元素):
    {{"intents": [{{"target": "qa" 或 "action" 或 "chitchat",
                   "strategy": "knowledge" 或 "compatibility" 或 "diagnosis" 或 null,
                   "question": "这一路要处理的那半句"}}]}}

    ★ 拆不拆的唯一判据:是否【分属不同处理单元】
    - 用户提的多件事若属于【同一处理单元】,合并成【一个】intent,question 填完整原句。
      例:"查一下订单12346到哪了,顺便约周日的保养" → 两件事都是 action,只返回 1 个 intent。
         (办业务的单元自己会连着办多件事,拆开反而多余)
    - 只有多件事【分属不同处理单元】时才拆成多个 intent,每个 intent 的 question
      只写属于它的那半句。
      例:"ninja400的火花塞是什么,帮我预约一下明天修车"
         → [{{"target":"qa","strategy":"compatibility","question":"ninja400的火花塞是什么"}},
            {{"target":"action","strategy":null,"question":"帮我预约一下明天修车"}}]
    - 单纯描述故障现象(哪怕提到多个症状)属于【同一处理单元】,不拆。
      例:"加速无力还异响" → 1 个 intent(qa/diagnosis),question 填原句。
    - 只有 1 个 intent 时,question 必须【原样照抄用户问题】,一个字都不许精简或改写
      (精简会丢掉"2020年""CPR8EA-9"这类检索锚点)。

    target 说明:
    - qa: 只读的信息查询,且答案在【手册/配件图谱/故障知识】里(查参数、查配件兼容、排查故障)。此时 strategy 必填。
    - action: 需要【执行操作】(查订单、预约保养、申请退换货、修改订单)。strategy 填 null。
    - chitchat: 闲聊、问候、感谢;以及【用户陈述自身情况】或【询问他自己先前说过的信息】
      (这类答案在对话历史里,不在手册里)。strategy 填 null。

    优先判据(先判这两条,再考虑 strategy):
    - 用户只是【陈述】自己的情况、并没有提问 → chitchat。
      例:"我骑的是 Ninja 400" / "我的车是 2019 款" / "我刚提了新车"
    - 用户问的是【他自己之前告诉过你的信息】→ chitchat。
      例:"我骑的是什么" / "我刚说的订单号是多少" / "你还记得我的车吗"
    - 句子里出现车型或配件名,不等于要查手册——先看用户真正想要什么。

    strategy 说明(仅 target=qa 时):
    - knowledge: 问某个数值参数/规格/保养周期,不涉及"查是哪个配件"。例:"火花塞电极间隙是多少"(问间隙数值) / "机油多久换一次"(问周期) / "轮胎气压多少"
    - compatibility: 查"车型↔配件"的配对关系,以下两种形态都算:
      ① 给定车型,问该用哪个配件/什么型号/货号/零件号。例:"2020款Ninja 400用什么火花塞" / "本田CB400用的机油滤清器货号是多少"
      ② 给定配件,反查能装哪些车。例:"CPR8EA-9还能装哪些车"
      判据:凡是要确定"具体哪一个配件、什么型号或货号"的都归此类,别因为问法是"货号/型号是多少"就误判成 knowledge。
      前提:问句里必须出现【具体车型】(如 Ninja 400、CB400、MT-07)或【具体配件型号】(如 CPR8EA-9)作为锚点;
      若两者都没有(只笼统问某类配件该用什么,如"该加什么标号的机油"),归 knowledge。
    - diagnosis: 描述故障现象、需要排查原因。例:"加速无力还异响"
{history_block}
    用户问题:{question}
    JSON:"""
    resp = llm.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
    try:
        d = RouteDecision.model_validate_json(text)
        if not d.intents:                      # 空数组能过 Pydantic 校验,但下游会拿到零条路
            raise ValueError("intents 为空")
        return d
    except (ValidationError, ValueError):
        # 兜底走 qa/knowledge(最安全:只读、有资料、不会误触发业务操作)
        return RouteDecision(intents=[Intent(target="qa", strategy="knowledge", question=question)])
    
# 礼貌前缀:中文客服里是个【封闭且稳定】的小集合。剥掉它属于「规范化」——
# 和 lowercase、去空白同类,不是又调一个阈值。
# 不剥的代价是实测出来的:"请问一下,你们几点开门" 会被切成 ["请问一下", "你们几点开门"],
# 而"请问一下"对 FAQ 的相似度 0.71 不达标 → 整句被踢出 FAQ 短路 → 兜底路径按
# _chitchat_reply 的 prompt("历史里没有的就如实说不知道")只能答"不知道"。
# 一个本该命中 FAQ 的正常问法,退化成答不出来。
_POLITE_PREFIX = r"^(请问一下|麻烦问一下|麻烦问下|想问一下|想问下|打听一下|咨询一下|请教一下|请问|问一下|问下|你好|您好|哈喽|嗨)[,，。!！、:：\s]*"

# 分句点:标点 + 高频连接词("另外/顺便/还有/此外/以及"后面通常正好跟着第二件事)
# + 换行 + 【夹在汉字之间的】空格。
# ⚠️ 单个空格【不能】无条件当分隔符:中文问句里的空格多半长在英文型号中间——
#    "Ninja 400"、"DID 520"、"NGK CPR8EA-9"。无条件切会把 compatibility 用例连同
#    整个图检索能力一起打碎("Ninja 400的火花塞" → ["Ninja","400的火花塞"])。
#    用前后向断言限定"两侧都是汉字"才切:那才是人为停顿,型号里的空格至少有一侧是字母数字。
_CLAUSE_SPLIT = (r"[,，。;；?？!！]|另外|顺便|还有|此外|以及|\n+"
                 r"|(?<=[一-鿿])[ \t]+(?=[一-鿿])")


def _subclauses(question: str) -> list[str]:
    """把问句切成子句。切不出东西(无标点的整句)就退化成原句本身——
    这保证了单句路径的行为与逐子句改造前【逐字节一致】。"""
    q = re.sub(_POLITE_PREFIX, "", question.strip())
    parts = [c.strip() for c in re.split(_CLAUSE_SPLIT, q) if c.strip()]
    return parts or [question.strip()]


def check_faq(question: str, threshold: float = 0.75) -> str | None:
    """FAQ 语义缓存。命中返回答案(可能是多条拼接),未命中返回 None。

    判据:**只有当每一个子句都被 FAQ 覆盖时,才允许 FAQ 短路整句。**

    为什么不能拿整句比(2026-07-26 修的真 bug):FAQ 短路发生在 decide_route【之前】,
    一命中就直接返回,多意图拆分根本没机会执行。而整句 encode 会把两件事揉进一个向量,
    实测"你们几点开门,顺便帮我查下订单12345"整句相似度 0.850 ≥ 0.75 → 命中 → 短路,
    **订单查询被静默丢弃**,而且答案读起来是完整一句话,用户根本察觉不到少了一半。

    为什么不是"提高阈值"就完了:实测【应命中的改写单句最低 0.820,复合句最高 0.851】,
    区间不只重叠、方向还反了(复合句分数高过改写单句),不存在可用阈值。根因是
    **整体语义相似度这个信号压根不携带「这句话里有几件事」的信息**——它衡量"整体像不像"。
    切成子句之后,信号维度才对上:每段各自纯粹,"有一段没人管"这个事实才显形。
    (坑 4 的镜像:那次是选错了模型,这次是选错了信号维度。信号对了,正则就够,不需要模型。)

    已知上限:依赖标点。"你们几点开门帮我查下订单12345"(完全不打标点)切不开,
    整句 0.81 仍会短路 → 仍会丢第二问。彻底解法是把 FAQ 降级到 intent 级(见 TODO),
    代价是每次都要先付一次路由 LLM 调用,当前不划算。
    """
    hits, rest = match_faq(question, threshold)
    return "\n".join(hits) if hits and not rest else None


def match_faq(question: str, threshold: float = 0.75) -> tuple[list[str], str]:
    """逐子句匹配的底座。返回 (命中的 FAQ 答案去重列表, 未被覆盖的子句拼成的问句)。

    三种结果,supervisor 分别处置:
    - 全覆盖  (答案, "")      → 短路,零 LLM 调用(FAQ 缓存的本职)
    - 部分覆盖 (答案, 余下问句) → FAQ 那段先入账当一路答案,余下问句交给路由拆意图,merge 缝合
    - 全不覆盖 ([], 原句)      → 照常走路由

    **"部分覆盖"这一支是必须的**(2026-07-26 实测):若命中的子句只是不再短路、答案却被丢掉,
    "你们几点开门,顺便查下订单12345" 会被整句交给路由 → 营业时间那半落到检索路径上,
    而营业时间不在手册里 → 答"没查到相关信息"。等于把"丢第二问"换成"第一问答错"。
    只把【未覆盖的子句】交给路由,还顺带修了误路由:实测整句交路由时"周末开门吗"会被判成 action。
    """
    subs = _subclauses(question)
    vecs = _embed_model.encode(subs)["dense_vecs"]
    hits, rest = [], []
    for sub, v in zip(subs, vecs):
        sim, idx = _max_similarity(v, _faq_vectors)
        if sim >= threshold:
            hits.append(_faq_answers[idx])
        else:
            rest.append(sub)
    # 多个子句各自命中不同 FAQ 时全部保留(去重保序)。只返最佳单条会漏:
    # "你们几点开门,电话是多少" 两段都命中,却只答得出营业时间。
    return list(dict.fromkeys(hits)), ",".join(rest)

# ==================== 意图分类 ====================
def classify_intent(question: str) ->str :
    """返回 chitchat / knowledge / diagnosis / compatibility 之一"""
    prompt = f"""你是摩托车客服系统的问题分类器。判断用户问题属于哪一类,只回答类别名,不要解释:
- chitchat: 闲聊、问候、感谢
- knowledge: 询问保养、参数、规格等知识性问题
- diagnosis: 描述故障现象、需要排查原因的复杂问题
- compatibility: 配件兼容查询,特征是"谁配谁"的关系判断:
  ① 给定确切车型(可含年份),问某个部位该用哪个配件。例:"2020款Ninja 400用什么火花塞"
  ② 给定确切配件型号,反查它能装在哪些车型上。例:"CPR8EA-9还能装哪些车"
  反例:只问配件自身的规格/参数(如"火花塞间隙是多少""机油多久换一次"),属于 knowledge,不属此类。
用户问题:{question}
类别:"""
    resp = llm.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    result = resp.choices[0].message.content.strip().lower()
    # 兜底:如果模型没老实返回三个词之一,默认走knowledge(最安全的默认)
    for valid in ["chitchat", "knowledge", "diagnosis","compatibility"]:
        if valid in result:
            return valid
    return "knowledge"

# ==================== 历史记忆合成 ====================
def rewrite_with_history(question: str, history: list[dict]) -> str:
    """用对话历史把指代性问题改写成独立问题。无历史或无指代则原样返回。"""
    if len(history) <= 1:
        return question               # 只有本轮问题、无更早上文,无需改写(省一次 LLM 调用)
    # TODO 你写:把 history + 当前 question 给 LLM,要求它输出一个"不依赖上下文也能懂"的独立问题
    #   prompt 要点:
    #   - 给出最近几轮对话 + 当前问题
    #   - 要求:如果当前问题含指代("那""它""这个")或省略,用历史补全成完整问题
    #   - 如果本身已完整,原样返回,不要画蛇添足
    #   - 只返回改写后的问题一句话,temperature=0
    prompt = f"""下面是最近的对话历史和用户当前的问题。请把当前问题改写成一个不依赖上下文、能独立理解的问题。
    - 若当前问题含指代(那/它/这个)或省略了主语,用历史补全成完整问题。
    - 若本身已完整,原样返回,不要改动。
    - 只输出改写后的问题本身,不要任何解释、引号或前缀。

    对话历史:
    {history}

    当前问题:{question}

    改写后的问题:"""
    resp = llm.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content.strip()

# ==================== 查询改写:HyDE ====================
def generate_hyde(question: str) -> str:
    """生成假设性答案,用作检索诱饵"""
    prompt = f"""针对下面的摩托车问题,写一段简短(2-3句)、专业书面的假设性答案。
不需完全准确,重点是用专业表达方式。

问题:{question}
假设性答案:"""
    resp = llm.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()

# ==================== 查询改写:子问题拆解 ====================
def decompose_query(question: str) -> list[str]:
    """复合问题拆成子问题列表,单一问题原样返回"""
    prompt = f"""判断下面的问题是否包含多个独立子问题。包含则拆解,单一则原样返回。
以JSON数组返回,只返回数组不要解释。

用户问题:{question}
拆解结果:"""
    resp = llm.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, list) and result else [question]
    except json.JSONDecodeError:
        return [question]   # 解析失败兜底
    
if __name__ == "__main__":
    tests = [
    ("qa/knowledge",      "火花塞的电极间隙是多少"),
    ("qa/compatibility",  "我2020年的Ninja 400能用什么火花塞"),
    ("qa/compatibility",  "NGK CPR8EA-9还能装哪些车"),
    ("qa/diagnosis",      "我的车最近加速无力还异响"),
    ("action",            "帮我查一下订单12345到哪了"),        # ← 新
    ("action",            "我想预约下周六做保养"),              # ← 新
    ("action",            "这个刹车片我要退货"),                # ← 新
    ("chitchat",          "谢谢"),
    ]
    for expect, q in tests:
        print(f"{q}\n  期望:{expect}  实际:{decide_route(q)}\n")