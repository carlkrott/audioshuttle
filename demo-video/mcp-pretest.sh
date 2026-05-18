#!/bin/bash

# mcp-pretest.sh
# Tests all 5 AudioShuttle MCP tools and generates a report

REPORT_FILE="/home/korphaus/audioshuttle/demo-video/mcp-test-results.md"
export PYTHONPATH="/home/korphaus/audioshuttle/src:$PYTHONPATH"

# We run a python script that instantiates the FastMCP server internally
# and calls the tools directly, accurately testing the MCP tool logic.
cat << 'EOF' > /tmp/mcp_tester_internal.py
import sys
import json
import time
import asyncio
from audioshuttle.config import Settings
from audioshuttle.server import create_server

async def test_tool(mcp, name, arguments, f):
    f.write(f"## Tool: `{name}`\n")
    f.write(f"**Command:** `mcp.call_tool('{name}', {json.dumps(arguments)})`\n")
    
    print(f"Testing {name}...")
    start_time = time.time()
    
    status = "✅ SUCCESS"
    output = ""
    try:
        # mcp.call_tool returns a CallToolResult
        result = await mcp.call_tool(name, arguments)
        
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
    # Pretty print the json if possible
    try:
        parsed = json.loads(output)
        f.write(f"{json.dumps(parsed, indent=2)}\n")
    except:
        f.write(f"{output}\n")
    f.write("```\n\n---\n")

async def main():
    settings = Settings()
    # We create the server with model_enabled=True to test the model translation
    mcp = create_server(settings)
    
    report_file = "/home/korphaus/audioshuttle/demo-video/mcp-test-results.md"
    
    with open(report_file, "w") as f:
        f.write("# AudioShuttle MCP Tool Preflight Report\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")
        import socket
        f.write(f"Host: {socket.gethostname()}\n\n")
        
        await test_tool(mcp, "daw_state", {}, f)
        await test_tool(mcp, "daw_command", {"command": "list all tracks"}, f)
        await test_tool(mcp, "daw_thinking", {"n": 50}, f)
        await test_tool(mcp, "daw_interrupt", {"reason": "preflight test"}, f)
        
        # Create a dummy file for the transcribe test
        with open("/tmp/dummy.wav", "w") as dummy:
            dummy.write("dummy")
            
        await test_tool(mcp, "transcribe_audio", {"audio_path": "/tmp/dummy.wav"}, f)

if __name__ == "__main__":
    asyncio.run(main())
EOF

echo "Running internal MCP tests..."
python3 /tmp/mcp_tester_internal.py
echo "Tests complete! Report written to $REPORT_FILE"
