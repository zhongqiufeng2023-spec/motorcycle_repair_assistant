import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
llm = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def decompose_query(question: str) -> list[str]:
    """把复合问题拆成独立的子问题列表"""
    prompt = f"""请判断下面的用户问题是否包含多个独立的子问题。
如果包含,把它拆解成若干个独立、完整的子问题;如果本身就是单一问题,原样返回。
以JSON数组格式返回,只返回数组,不要解释。

用户问题:{question}

示例输出格式:["子问题1", "子问题2"]

拆解结果:"""
    resp = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    # LLM可能返回带```json的代码块,清理一下
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  (解析失败,原样返回。LLM输出:{text})")
        return [question]   # 兜底:解析失败就当单一问题

# 测试
for q in [
    "Ninja 400该用什么机油、多久换一次、自己换难不难",
    "火花塞型号是什么",   # 单一问题,应该原样返回
]:
    subs = decompose_query(q)
    print(f"原问题:{q}")
    print(f"拆解为 {len(subs)} 个子问题:")
    for s in subs:
        print(f"  - {s}")
    print()