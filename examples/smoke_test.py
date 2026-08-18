"""Smoke test: MCP stdio handshake against mcp_server.py, listing tools."""
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
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("TOOLS:", ", ".join(names))
            print("HANDSHAKE_OK")


if __name__ == "__main__":
    asyncio.run(main())
