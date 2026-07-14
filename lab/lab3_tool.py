import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

# 工具本体:就是个普通Python函数
def calculator(expression: str) -> str:
    return str(eval(expression)) 

tools = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "A simple calculator that evaluates mathematical expressions",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]

user_input = input("请输入数学表达式:")
messages = [{"role": "user", "content": user_input}]
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    tools=tools
)
msg = response.choices[0].message
print(msg)
messages.append(msg.model_dump())
if msg.tool_calls:
    call = msg.tool_calls[0]
    args = json.loads(call.function.arguments)     # 参数是JSON字符串,要解析
    result = calculator(**args)
    print("你执行的结果:", result)

    messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    resp2 = client.chat.completions.create(model="deepseek-chat", messages=messages, tools=tools)
    print("最终回答:", resp2.choices[0].message.content)
else:
    print("没有调用工具,直接回答:", msg.content)