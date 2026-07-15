import os,sys
from dotenv import load_dotenv
from openai import OpenAI
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.moto_manual import DOCS
from app.retriever import HybridRetriever
load_dotenv()
llm = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
retriever = HybridRetriever(DOCS, chroma_path=os.path.join(BASE_DIR, "chroma_db"))

def generate_hyde(question: str) -> str:
    """让LLM根据问题编一段'假想答案',用来当检索诱饵"""
    prompt = f"""请针对下面这个摩托车相关的问题,写一段简短的、专业的假设性答案。
不需要保证完全准确,重点是用专业、书面的表达方式描述可能的答案。
控制在2-3句话。

问题:{question}

假设性答案:"""
    resp = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,   # 稍微给点灵活性,但别太发散
    )
    return resp.choices[0].message.content

# 对比:原始问题 vs HyDE假答案
question = "我这车冬天早上很难打着火,咋回事"
hyde = generate_hyde(question)
print(f"原始问题(口语):\n  {question}\n")
print(f"HyDE假想答案(专业文风,用来检索):\n  {hyde}")

print("\n用【原始问题】检索:")
for d in retriever.retrieve(question, top_k=3):
    print("  -", d)

print("\n用【HyDE假答案】检索:")
for d in retriever.retrieve(hyde, top_k=3):
    print("  -", d)