from FlagEmbedding import BGEM3FlagModel
import chromadb, os

model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
client = chromadb.PersistentClient(path=os.path.join(BASE_DIR, "data", "chroma_db"))
collection = client.get_collection("manual")   # 注意是get,不是create

def search(question: str, top_k: int = 4):
    q_vector = model.encode([question])['dense_vecs']
    results = collection.query(
        query_embeddings=[q_vector[0].tolist()],  # 同样要转list
        n_results=top_k,
    )
    return results

question = "火花塞CPR8EA-9的电极间隙"
res = search(question)

print(f"问题:{question}\n")
print("找回的相关知识:")
# Chroma返回的结构:documents和distances都是"嵌套列表",取[0]拿到第一个问题的结果
docs = res["documents"][0]
dists = res["distances"][0]
paired = sorted(zip(docs, dists), key=lambda x: x[1])
for doc, dist in paired:
    print(f"  [距离 {dist:.3f}] {doc}")