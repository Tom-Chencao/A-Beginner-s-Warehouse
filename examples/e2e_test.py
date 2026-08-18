"""End-to-end: MCP call tavily_search through the key pool."""
import asyncio
import sys

sys.path.insert(0, r"C:\Users\ASUS\.dsh\tavily-pool")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=r"D:\Downloads\Tavily\.venv\Scripts\python.exe",
        args=["mcp_server.py"],
        cwd=r"C:\Users\ASUS\.dsh\tavily-pool",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "tavily_search",
                {"query": "DeepSeek Harness", "max_results": 3, "include_usage": True},
            )
            for block in result.content:
                if block.type == "text":
                    text = block.text
                    import json
                    try:
                        data = json.loads(text)
                        print("RESULTS:", len(data.get("results", [])))
                        for r in data.get("results", [])[:3]:
                            print("-", r.get("title", "")[:60])
                        print("USAGE:", data.get("usage"))
                    except Exception:
                        print(text[:500])
            print("CALL_OK")


if __name__ == "__main__":
    asyncio.run(main())
