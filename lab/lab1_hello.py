import os
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()
MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")

client = OpenAI(
    api_key = os.getenv("DEEPSEEK_API_KEY"),
    base_url = "https://api.deepseek.com"
)

response = client.chat.completions.create(
    model = MODEL,
    messages = [
        {"role": "system", "content": "你是一个会说胡话的助手"},
        {"role": "user", "content": "用一句话解释什么是API"},
    ],
)

print(response.choices[0].message.content)

