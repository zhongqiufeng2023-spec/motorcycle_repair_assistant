from FlagEmbedding import BGEM3FlagModel
import numpy as np

model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

FAQ_CACHE = {
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
faq_questions = []
faq_answers = []
for answer, questions in FAQ_CACHE.items():
    for q in questions:
        faq_questions.append(q)
        faq_answers.append(answer)
faq_vectors = model.encode(faq_questions)['dense_vecs']

def check_faq(question:str,threshold: float = 0.75) -> str | None:
    q_vec = model.encode([question])['dense_vecs'][0]
    sims = [np.dot(q_vec, fv) / (np.linalg.norm(q_vec) * np.linalg.norm(fv))for fv in faq_vectors]
    best_idx = int(np.argmax(sims))
    best_sim = sims[best_idx]
    print(f"  (最相似FAQ:'{faq_questions[best_idx]}' 相似度{best_sim:.3f})")
    if best_sim >= threshold:
        return faq_answers[best_idx]
    return None

for q in ["你们几点关门", "这个能退货吗", "机油拧多紧"]:
    hit = check_faq(q)
    print(f"问题:{q}")
    print(f"  {'命中FAQ → ' + hit if hit else '未命中,走正常RAG流程'}\n")
