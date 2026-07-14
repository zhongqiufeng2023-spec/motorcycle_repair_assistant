import os
from dotenv import load_dotenv
from openai import OpenAI
from FlagEmbedding import BGEM3FlagModel
import chromadb

load_dotenv()

client_llm = OpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "chroma_db")
db_client = chromadb.PersistentClient(path=DB_PATH)
collection = db_client.get_collection("manual")


def search(question: str, top_k: int = 3):
    q_vector = model.encode([question])['dense_vecs']
    results = collection.query(
        query_embeddings=[q_vector[0].tolist()],
        n_results=top_k,
    ) 
    docs = results["documents"][0]
    dists = results["distances"][0]
    for d, dist in zip(docs, dists):
        print(f"  [距离{dist:.3f}] {d[:30]}...")
    return docs


def rag_answer(question: str):
    contexts = search(question)
    context_text = "\n".join(f"= {c}" for c in contexts)
    # prompt = f" 【参考资料】{context_text}【用户问题】{question}"
    prompt = f""""你是一个Ninja400的汽修助手，请严格根据下面提供的资料回答用户问题。如果资料中没有相关信息,就如实说手册里没有查到相关信息",不要编造。
【参考资料】
{context_text}

【用户问题】
{question}"""

    resp = client_llm.chat.completions.create(
        model="deepseek-chat",
        messages = [{"role":"user", "content":prompt}] 
    )
    return resp.choices[0].message.content, contexts

if __name__ == "__main__":
    # 测试1:库里有答案的问题
    print("=" * 50)
    question = "我换机油的时候放油螺丝拧多紧比较合适?"
    answer, used = rag_answer(question)
    print(f"问题:{question}\n")
    print("AI回答:\n", answer)
    print("\n(基于这些资料:)")
    for u in used:
        print("  -", u)

    # 测试2:库里没有答案的问题,检验它会不会老实承认
    print("\n" + "=" * 50)
    question2 = "什么咖啡比较好喝"
    answer2, used2 = rag_answer(question2)
    print(f"问题:{question2}\n")
    print("AI回答:\n", answer2)