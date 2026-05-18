import asyncio
import json
import time
from typing import Any
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def test_tool(session: ClientSession, name: str, arguments: dict[str, Any], f):
    f.write(f"## Tool: `{name}`\n")
    f.write(f"**Command:** `mcp call {name} '{json.dumps(arguments)}'`\n")
    
    print(f"Testing {name}...")
    start_time = time.time()
    
    status = "✅ SUCCESS"
    output = ""
    try:
        result = await session.call_tool(name, arguments=arguments)
        # result is typically a CallToolResult with content list
        output_parts = []
        for item in result.content:
            if item.type == "text":
                output_parts.append(item.text)
        output = "\n".join(output_parts)
    except Exception as e:
        status = f"❌ FAILURE (Exception: {str(e)})"
        output = str(e)
        
    end_time = time.time()
    rtt = int((end_time - start_time) * 1000)
    
    f.write(f"**Status:** {status}\n")
    f.write(f"**Round-trip Time:** {rtt}ms\n\n")
    f.write("**Response:**\n```json\n")
    f.write(f"{output}\n")
    f.write("```\n\n---\n")

async def main():
    report_file = "/home/korphaus/audioshuttle/demo-video/mcp-test-results.md"
    
    with open(report_file, "w") as f:
        f.write("# AudioShuttle MCP Tool Preflight Report\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")
        f.write("Host: 7995x-cachyos\n\n")
        
        url = "http://localhost:8765/sse"
        print(f"Connecting to {url}...")
        try:
            async with sse_client(url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    await test_tool(session, "daw_state", {}, f)
                    await test_tool(session, "daw_command", {"command": "list all tracks"}, f)
                    await test_tool(session, "daw_thinking", {"n": 50}, f)
                    await test_tool(session, "daw_interrupt", {"reason": "preflight test"}, f)
                    await test_tool(session, "transcribe_audio", {"audio_path": "/tmp/dummy.wav"}, f)
        except Exception as e:
            f.write(f"## Connection Error\n```\n{str(e)}\n```\n")
            print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
