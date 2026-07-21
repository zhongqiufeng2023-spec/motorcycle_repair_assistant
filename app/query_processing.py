import os, json
from dotenv import load_dotenv
from openai import OpenAI
from FlagEmbedding import BGEM3FlagModel
import numpy as np
from typing import Literal, Optional
from pydantic import BaseModel, ValidationError
from langsmith.wrappers import wrap_openai

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
    - yes(是投诉):对本店的服务、态度、质量、处理效率表达不满或愤怒。
    例:"客服态度太差了,一直推脱" / "修了三次还没修好" / "太坑了,退钱"
    - no(不是投诉):
    · 只是描述车辆故障,哪怕用词很负面。例:"我的刹车失灵了,太危险了" / "车子异响,烦死了"
    · 表达感谢或称赞。例:"你们服务真不错"
    · 普通技术咨询。例:"机油多久换一次"

    用户的话:{question}
    回答(yes/no):"""
    resp = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    # 兜底:LLM 没老实回 yes/no 就当作"不是投诉",走正常流程(至少能给用户答案)
    return resp.choices[0].message.content.strip().lower().startswith("yes")

# ==================== 路由决策 ====================
class RouteDecision(BaseModel):
    target: Literal["qa", "action", "chitchat", "complaint"]
    strategy: Optional[Literal["knowledge", "compatibility", "diagnosis"]] = None

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

    返回格式:
    {{"target": "qa" 或 "action" 或 "chitchat", "strategy": "knowledge" 或 "compatibility" 或 "diagnosis" 或 null}}

    target 说明:
    - qa: 只读的信息查询(查手册参数、查配件兼容、排查故障)。此时 strategy 必填。
    - action: 需要【执行操作】(查订单、预约保养、申请退换货、修改订单)。strategy 填 null。
    - chitchat: 闲聊、问候、感谢。strategy 填 null。

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
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
    try:
        return RouteDecision.model_validate_json(text)
    except (ValidationError, ValueError):
        return RouteDecision(target="qa", strategy="knowledge")
    
def check_faq(question :str, threshold: float = 0.75) -> str | None:
    q_vec = _embed_model.encode([question])['dense_vecs'][0]

    # print("q_vec shape:", np.array(q_vec).shape)          # 期望 (dim,),比如 (1024,)
    # print("faq_vec shape:", np.array(_faq_vectors[0]).shape)  # 也应是 (dim,)
    # print("faq count:", len(_faq_vectors))
    
    best_sim, best = _max_similarity(q_vec, _faq_vectors)
    if best_sim >= threshold:
        return _faq_answers[best]
    return None

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
        model="deepseek-chat",
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
        model="deepseek-chat",
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
        model="deepseek-chat",
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
        model="deepseek-chat",
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