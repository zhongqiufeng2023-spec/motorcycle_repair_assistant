import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

llm = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url = "https://api.deepseek.com")


def classify_intent(question:str) -> str:
    prompt = f"""你是一个摩托车客服系统的问题分类器。请判断用户问题属于以下哪一类,只回答类别名,不要解释:

- chitchat: 闲聊、问候、感谢,不涉及具体车辆知识(如"你好""谢谢""你是谁")
- knowledge: 询问车辆的保养、参数、规格等知识性问题(如"机油拧多紧""火花塞型号")
- diagnosis: 描述故障现象、需要排查原因的复杂问题(如"跑高速时车头抖动怎么回事")

用户问题:{question}

类别:"""
    resp = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,   # 分类任务要稳定,不要随机性
    )
    return resp.choices[0].message.content.strip()

for q in ["你们店几点关门", "机油多少钱", "我的Ninja跑到120就开始抖,是什么问题"]:
    print(f"[{classify_intent(q)}]  {q}")