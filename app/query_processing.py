import os, json
from dotenv import load_dotenv
from openai import OpenAI
from FlagEmbedding import BGEM3FlagModel
import numpy as np

load_dotenv()
llm = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url = "https://api.deepseek.com")
# FAQ匹配要用向量,复用BGE-M3
_embed_model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
# ==================== FAQ 匹配 ====================
FAQ_DATA = {
        "本店营业时间为周一至周六 9:00-18:00,周日休息。": [
        "你们几点营业", "营业时间是什么时候", "周末开门吗", "礼拜天上班吗"
    ],
    "配件类商品未拆封状态下 7 天内可退货,请保留购买凭证。": [
        "怎么退货", "退货政策是什么", "买的东西能退吗"
    ],
    "客服热线:400-xxx-xxxx。": [
        "客服电话多少", "怎么联系你们", "有没有联系方式"
    ],
}

_faq_questions, _faq_answers = [], []
for _ans, _qs in FAQ_DATA.items():
    for q in _qs:
        _faq_questions.append(q)
        _faq_answers.append(_ans)
_faq_vectors = _embed_model.encode(_faq_questions)['dense_vecs']

def check_faq(question :str, threshold: float = 0.75) -> str | None:
    q_vec = _embed_model.encode([question])['dense_vecs'][0]

    # print("q_vec shape:", np.array(q_vec).shape)          # 期望 (dim,),比如 (1024,)
    # print("faq_vec shape:", np.array(_faq_vectors[0]).shape)  # 也应是 (dim,)
    # print("faq count:", len(_faq_vectors))
    sims = [np.dot(q_vec, fv)/(np.linalg.norm(q_vec)*np.linalg.norm(fv)) for fv in _faq_vectors]

    # print("sims shape:", np.array(sims).shape) 
    best = int(np.argmax(sims))
    if sims[best] >= threshold:
        return _faq_answers[best]
    return None

# ==================== 意图分类 ====================
def classify_intent(question: str) ->str :
    """返回 chitchat / knowledge / diagnosis 之一"""
    prompt = f"""你是摩托车客服系统的问题分类器。判断用户问题属于哪一类,只回答类别名,不要解释:
- chitchat: 闲聊、问候、感谢
- knowledge: 询问保养、参数、规格等知识性问题
- diagnosis: 描述故障现象、需要排查原因的复杂问题

用户问题:{question}
类别:"""
    resp = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    result = resp.choices[0].message.content.strip().lower()
    # 兜底:如果模型没老实返回三个词之一,默认走knowledge(最安全的默认)
    for valid in ["chitchat", "knowledge", "diagnosis"]:
        if valid in result:
            return valid
    return "knowledge"

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