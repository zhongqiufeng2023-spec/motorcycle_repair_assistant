import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def calculator(expression: str) -> str:
    return str(eval(expression))

TOOLS_IMPL = {"calculator": calculator}          # 名字→函数 的登记表
tools = [ {
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
    } ]   # ← 把第3关的说明书原样搬过来

def run_agent(question:str , max_turns:int = 10):
    messages = [{"role":"user", "content": question}]
    for turn in range(max_turns):
        response = client.chat.completions.create(
            model = "deepseek-chat",
            messages = messages,
            tools = tools
        )

        msg = response.choices[0].message
        if msg.tool_calls:
            
        
            messages.append(msg.model_dump())
            for call in msg.tool_calls:                     
                func_name = call.function.name
                args = json.loads(call.function.arguments)
                func = TOOLS_IMPL[func_name]
                result = func(**args)
                print(f"第{turn+1}轮，执行 {call.function.name}({args}) = {result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,     
                    "content": str(result),
                })
        else:
            return msg.content
    return "达到最大轮数"
user_input = input("请输入问题: ")
print(run_agent(user_input))

