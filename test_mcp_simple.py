#!/usr/bin/env python3
"""
Simple MCP tools test using known UUID.
"""

import requests
import json
import tempfile
import os

def test_mcp_tools():
    """Simple test of MCP tools using local server."""
    
    # Use the UUID from .vibecode.json
    mcp_url = "http://localhost:8396/2cc4691f9159477f95a4d7f57a3ea1e9"
    
    print(f"Testing MCP tools at: {mcp_url}")
    
    # Test 1: Initialize
    print("\n1. Testing initialize...")
    try:
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
            timeout=5
        )
        
        print(f"Initialize response: {response.status_code}")
        if response.status_code == 200:
            print("✅ Initialize works")
        else:
            print(f"❌ Initialize failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Initialize failed with exception: {e}")
        return False
    
    # Test 2: List tools
    print("\n2. Testing tools/list...")
    try:
        response = requests.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 2,
                "params": {}
            },
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        
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
                print(f"✅ Found {len(tools)} tools:")
                for name in sorted(tool_names):
                    print(f"   - {name}")
                return True
            else:
                print(f"❌ Could not parse tools: {tools_data}")
                return False
        else:
            print(f"❌ Tools list failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Tools list failed with exception: {e}")
        return False

if __name__ == "__main__":
    import subprocess
    import sys
    import time
    
    print("🚀 Starting simple MCP test...")
    
    # Start server
    print("Starting vibecode server...")
    server_proc = subprocess.Popen([
        sys.executable, "-m", "vibecode.cli", "start",
        "--no-tunnel", "--port", "8396", "--no-auth"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        # Wait for server
        time.sleep(8)
        
        # Run test
        success = test_mcp_tools()
        
        if success:
            print("\n🎉 MCP tools test PASSED!")
        else:
            print("\n❌ MCP tools test FAILED!")
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server_proc.kill()