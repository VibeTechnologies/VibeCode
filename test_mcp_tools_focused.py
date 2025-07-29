#!/usr/bin/env python3
"""
Focused test for MCP tools that works with the actual server structure.
"""

import subprocess
import sys
import time
import requests
import json
import tempfile
import os
import uuid
import re


def get_server_uuid_from_output(server_process, timeout=10):
    """Extract the UUID from server output."""
    start_time = time.time()
    uuid_pattern = re.compile(r'[a-f0-9]{32}')
    
    while time.time() - start_time < timeout:
        try:
            # Read from stdout
            line = server_process.stdout.readline()
            if line:
                match = uuid_pattern.search(line)
                if match:
                    return match.group(0)
            
            # Check if process is still running
            if server_process.poll() is not None:
                break
                
        except Exception:
            break
        
        time.sleep(0.1)
    
    return None


def test_mcp_tools_with_local_server():
    """Test MCP tools with local server."""
    print("🚀 Starting focused MCP tools test...")
    
    # Start server in background
    print("Starting vibecode server...")
    server_proc = subprocess.Popen([
        sys.executable, "-m", "vibecode.cli", "start",
        "--no-tunnel", "--port", "8395", "--no-auth"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    try:
        # Wait for server to start and get UUID
        time.sleep(5)
        
        # Try to read the UUID from the initial output
        initial_output = server_proc.stdout.read()
        print(f"Server initial output: {initial_output}")
        
        # Extract UUID from output
        uuid_match = re.search(r'http://localhost:8395/([a-f0-9]{32})', initial_output)
        if uuid_match:
            server_uuid = uuid_match.group(1)
            print(f"Found server UUID: {server_uuid}")
        else:
            # Try reading from .vibecode.json
            try:
                with open('.vibecode.json', 'r') as f:
                    config = json.load(f)
                    server_uuid = config.get('uuid')
                    print(f"Got UUID from config: {server_uuid}")
            except:
                print("Could not determine server UUID, using test UUID")
                server_uuid = "test"
        
        mcp_url = f"http://localhost:8395/{server_uuid}"
        print(f"Using MCP URL: {mcp_url}")
        
        # Test 1: Initialize
        print("\n1. Testing initialize...")
        response = requests.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": 1,
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"Initialize response: {response.status_code}")
        if response.status_code == 200:
            print("✅ Initialize works")
        else:
            print(f"❌ Initialize failed: {response.text}")
            return
        
        # Test 2: List tools
        print("\n2. Testing tools/list...")
        response = requests.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 2,
                "params": {}
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"Tools list response: {response.status_code}")
        if response.status_code == 200:
            # Parse SSE response
            tools_data = None
            if "text/event-stream" in response.headers.get("content-type", ""):
                for line in response.text.split('\n'):
                    if line.startswith('data: '):
                        tools_data = json.loads(line[6:])
                        break
            else:
                tools_data = response.json()
            
            if tools_data and "result" in tools_data:
                tools = tools_data["result"]["tools"]
                tool_names = [tool["name"] for tool in tools]
                print(f"✅ Found {len(tools)} tools: {tool_names}")
                
                # Test 3: Test a simple tool (think)
                print("\n3. Testing think tool...")
                response = requests.post(
                    mcp_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "id": 3,
                        "params": {
                            "name": "think",
                            "arguments": {
                                "query": "Test query for MCP tool"
                            }
                        }
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=15
                )
                
                print(f"Think tool response: {response.status_code}")
                if response.status_code == 200:
                    print("✅ Think tool works")
                else:
                    print(f"❌ Think tool failed: {response.text}")
                
                # Test 4: Test file operation tools
                print("\n4. Testing file operations...")
                with tempfile.TemporaryDirectory() as temp_dir:
                    test_file = os.path.join(temp_dir, "test.txt")
                    
                    # Test write
                    response = requests.post(
                        mcp_url,
                        json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "id": 4,
                            "params": {
                                "name": "write",
                                "arguments": {
                                    "file_path": test_file,
                                    "content": "Hello from MCP test!"
                                }
                            }
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        print("✅ Write tool works")
                        
                        # Test read
                        response = requests.post(
                            mcp_url,
                            json={
                                "jsonrpc": "2.0",
                                "method": "tools/call",
                                "id": 5,
                                "params": {
                                    "name": "read",
                                    "arguments": {
                                        "file_path": test_file
                                    }
                                }
                            },
                            headers={"Content-Type": "application/json"},
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            print("✅ Read tool works")
                        else:
                            print(f"❌ Read tool failed: {response.text}")
                    else:
                        print(f"❌ Write tool failed: {response.text}")
                
                # Test 5: Test command tool
                print("\n5. Testing run_command tool...")
                response = requests.post(
                    mcp_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "id": 6,
                        "params": {
                            "name": "run_command",
                            "arguments": {
                                "command": "echo 'Hello from MCP command'"
                            }
                        }
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                
                if response.status_code == 200:
                    print("✅ Run command tool works")
                else:
                    print(f"❌ Run command tool failed: {response.text}")
                
                # Test 6: Test claude_code tool
                print("\n6. Testing claude_code tool...")
                response = requests.post(
                    mcp_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "id": 7,
                        "params": {
                            "name": "claude_code",
                            "arguments": {
                                "prompt": "What is the current date and time?",
                                "workFolder": temp_dir
                            }
                        }
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=20
                )
                
                if response.status_code == 200:
                    print("✅ Claude code tool works")
                else:
                    print(f"❌ Claude code tool failed: {response.text}")
                
                print("\n🎉 MCP tools test completed!")
            else:
                print(f"❌ Could not parse tools list: {tools_data}")
        else:
            print(f"❌ Tools list failed: {response.text}")
    
    finally:
        # Cleanup
        print("\nCleaning up server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


if __name__ == "__main__":
    test_mcp_tools_with_local_server()