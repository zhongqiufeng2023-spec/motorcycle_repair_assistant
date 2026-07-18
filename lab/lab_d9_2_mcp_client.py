import asyncio
from fastmcp import Client

async def main():
    async with Client("lab/lab_d9_1_mcp_server.py") as client:
        tools = await client.list_tools()          # ← 动态发现!
        for tool in tools:
            print(f"发现工具: {tool.name} — {tool.description}")
        result = await client.call_tool("query_order", {"order_id": "12345"})
        print(result)

asyncio.run(main())