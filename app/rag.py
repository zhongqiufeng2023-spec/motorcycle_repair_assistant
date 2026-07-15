import os, sys
from dotenv import load_dotenv
from openai import OpenAI
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.moto_manual import DOCS
from app.retriever import HybridRetriever
from app.query_processing import check_faq, classify_intent, generate_hyde, decompose_query

load_dotenv()
llm = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=os.getenv("BASE_URL"))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
retriever = HybridRetriever(DOCS, chroma_path = os.path.join(BASE_DIR,"data","chroma_db"))


def _generate(question: str, contexts: list[str]) ->str:
    """给定问题和检索到的资料,生成最终回答"""
    context_text = "\n".join(f"- {c}" for c in contexts)
    prompt = f"""你是Ninja 400的汽修助手。请严格根据下面的资料回答用户问题。
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

def route_and_answer(question: str) -> dict:
    """完整流水线:FAQ → 分类 → 按类分流"""

    # ---- 第①层:FAQ 缓存 ----
    faq = check_faq(question)
    if faq:
        return {"route": "FAQ", "answer": faq, "contexts": []}

    # ---- 第②层:意图分类 ----
    intent = classify_intent(question)

    # ---- 第③层:按意图分流 ----
    if intent == "chitchat":
        return {"route": "chitchat", "answer": _chitchat_reply(question), "contexts": []}

    if intent == "knowledge":
        # 普通知识问题:直接混合检索 → 生成
        contexts = retriever.retrieve(question, top_k=3)
        return {"route": "knowledge", "answer": _generate(question, contexts), "contexts": contexts}

    if intent == "diagnosis":
        # 复杂问题:先改写,再检索
        # 策略1:先拆解成子问题
        sub_questions = decompose_query(question)
        # 策略2:每个子问题用HyDE生成诱饵,分别检索,汇总资料
        all_contexts = []
        for sub_q in sub_questions:
            hyde = generate_hyde(sub_q)
            ctxs = retriever.retrieve(hyde, top_k=2)   # 每个子问题少取几条,避免总量爆炸
            all_contexts.extend(ctxs)
        # 去重(不同子问题可能检索到同一条)
        all_contexts = list(dict.fromkeys(all_contexts))
        return {"route": "diagnosis", "answer": _generate(question, all_contexts),
                "contexts": all_contexts, "sub_questions": sub_questions}


if __name__ == "__main__":
    tests = [
        "你们周日营业吗",                              # → FAQ
        "谢谢你的帮助",                                # → chitchat
        "火花塞CPR8EA-9的电极间隙是多少",              # → knowledge
        "我的Ninja该用什么机油、多久换一次、自己换难不难",  # → diagnosis
    ]
    for q in tests:
        print("=" * 60)
        print(f"问题:{q}")
        result = route_and_answer(q)
        print(f"走的路线:【{result['route']}】")
        if result.get("sub_questions"):
            print(f"拆解的子问题:{result['sub_questions']}")
        print(f"回答:{result['answer']}")
        if result["contexts"]:
            print(f"依据资料:{len(result['contexts'])}条")