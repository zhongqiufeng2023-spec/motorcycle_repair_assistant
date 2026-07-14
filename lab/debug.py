# 先测 embedding(高版本 transformers 下,应该正常)
from FlagEmbedding import BGEM3FlagModel
model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
emb = model.encode(["测试"])['dense_vecs']
print("✓ embedding 成功,维度:", len(emb[0]))

# 再测 reranker(改用 CrossEncoder,躲开 FlagEmbedding 的老方法)
from sentence_transformers import CrossEncoder
reranker = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512)
scores = reranker.predict([
    ["火花塞间隙多少", "Ninja400火花塞电极间隙0.8到0.9毫米"],
    ["火花塞间隙多少", "Ninja400轮胎气压前轮2.0bar"],
])
print("✓ reranker 成功,打分:", scores)