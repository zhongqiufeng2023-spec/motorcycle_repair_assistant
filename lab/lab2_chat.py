import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key = os.getenv("DEEPSEEK_API_KEY"),
    base_url = "https://api.deepseek.com" 
)

def ask(messages):
    response = client.chat.completions.create(
        model = "deepseek-chat",
        messages = messages
    )
    return response.choices[0].message.content

messages = [{"role":"system", "content":"你是一个汽修助手"}]

while True:
    user_input = input("\n你:")
    if user_input.lower() in ("exit","quit"):
        print ("退出聊天")
        break
    messages.append({"role":"user", "content": user_input})
    response = ask(messages)
    messages.append({"role":"assistant", "content":response})
    print(f"\nAI:{response}")
