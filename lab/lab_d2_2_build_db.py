from FlagEmbedding import BGEM3FlagModel
import chromadb
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from data.moto_manual import DOCS

# 1. 加载embedding模型(不变)
print("加载模型...")
model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

# 2. 把知识向量化(不变)
print("向量化知识库...")
vectors = model.encode(DOCS)['dense_vecs']

# 3. 连接Chroma:PersistentClient会把数据落到本地文件夹,重启不丢
client = chromadb.PersistentClient(path="./chroma_db")

# 4. 建collection。每次重跑先删,方便调试
if "manual" in [c.name for c in client.list_collections()]:
    client.delete_collection("manual")
collection = client.create_collection(name="manual")

# 5. 按Chroma的"平行列表"格式入库
collection.add(
    ids=[str(i) for i in range(len(DOCS))],   # 注意:Chroma的id必须是字符串
    embeddings=[v.tolist() for v in vectors],  # numpy数组要转成普通list
    documents=DOCS,                            # 原文
)
print(f"入库完成,共 {len(DOCS)} 条知识")