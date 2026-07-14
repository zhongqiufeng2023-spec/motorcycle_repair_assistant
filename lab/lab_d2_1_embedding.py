from FlagEmbedding import BGEM3FlagModel
import numpy as np

print("加载模型中,第一次会慢一点...")
model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

def similarity(a, b):
    # 余弦相似度:两个向量夹角的cos值,越接近1意思越像
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

sentences = [
    "换机油的时候放油螺丝要拧多紧",
    "放油螺栓的扭矩规格是多少",
    "今天悉尼天气怎么样",
]



embeddings = model.encode(sentences)['dense_vecs']

print("每句话变成了一个长度为", len(embeddings[0]), "的向量")
print("第一句的前5个数字:", embeddings[0][:5])
print("\n【换机油拧多紧】 vs 【放油螺栓扭矩】:", round(similarity(embeddings[0], embeddings[1]), 3))
print("【换机油拧多紧】 vs 【悉尼天气】    :", round(similarity(embeddings[0], embeddings[2]), 3))