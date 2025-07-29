"""REAL End-to-End test that actually tests Cloudflare tunnels with the CLI."""

import subprocess
import sys
import time
import threading
import re
import requests
import json
import pytest
from pathlib import Path


def test_real_vibecode_cli_with_tunnel():
    """The ONLY test that actually tests the real production flow."""
    
    print("🚀 REAL E2E TEST: Starting vibecode CLI with actual tunnel...")
    
    # Start the real CLI command with quick tunnel
    proc = subprocess.Popen([
        sys.executable, '-m', 'vibecode.cli', 'start', '--quick', '--port', '8500'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    
    tunnel_url = None
    uuid_path = None
    
    def read_output():
        """Read output to capture tunnel URL and UUID path."""
        nonlocal tunnel_url, uuid_path
        
        base_tunnel_url = None
        
        try:
            for line in iter(proc.stderr.readline, ''):
                print(f"SERVER OUTPUT: {line.strip()}")
                
                # Look for tunnel URL
                if 'trycloudflare.com' in line:
                    url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
                    if url_match:
                        base_tunnel_url = url_match.group(0)
                        print(f"🔗 Found tunnel URL: {base_tunnel_url}")
                
                # Look for UUID path  
                if 'MCP at' in line or 'endpoint ready at' in line:
                    uuid_match = re.search(r'/([a-f0-9]{32})', line)
                    if uuid_match:
                        uuid_path = uuid_match.group(1)
                        if base_tunnel_url:
                            tunnel_url = f"{base_tunnel_url}/{uuid_path}"
                            print(f"🔗 Complete tunnel URL: {tunnel_url}")
                            break
                        else:
                            print(f"🔗 Found UUID path: /{uuid_path}, waiting for tunnel URL...")
                
                # Also check for the complete URL format that might be printed together
                complete_url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com/[a-f0-9]{32}', line)
                if complete_url_match:
                    tunnel_url = complete_url_match.group(0)
                    print(f"🔗 Found complete tunnel URL: {tunnel_url}")
                    break
                        
        except Exception as e:
            print(f"❌ Error reading output: {e}")
    
    # Start output reader in background
    output_thread = threading.Thread(target=read_output, daemon=True)
    output_thread.start()
    
    try:
        # Wait for tunnel to be established (up to 60 seconds)
        print("⏳ Waiting for tunnel to be established...")
        for i in range(60):
            if tunnel_url:
                break
            time.sleep(1)
            if i % 10 == 0:
                print(f"⏳ Still waiting... ({i}s)")
        
        if not tunnel_url:
            pytest.fail("❌ FAILED: Could not extract tunnel URL from CLI output")
        
        print(f"✅ Tunnel established: {tunnel_url}")
        
        # Wait much longer for tunnel to be fully ready (Cloudflare needs time)
        print("⏳ Waiting for tunnel to become accessible...")
        time.sleep(30)  # Increased wait time
        
        # Test 1: Health check with retries
        print("🔍 Testing health endpoint...")
        health_success = False
        for attempt in range(3):
            try:
                health_response = requests.get(f"{tunnel_url.split('/' + uuid_path)[0]}/health", timeout=15)
                print(f"Health response (attempt {attempt+1}): {health_response.status_code}")
                if health_response.status_code == 200:
                    health_success = True
                    break
                else:
                    print(f"❌ Health check failed (attempt {attempt+1}): {health_response.text[:200]}...")
                    time.sleep(10)
            except Exception as e:
                print(f"⚠️ Health check failed (attempt {attempt+1}): {e}")
                time.sleep(10)
        
        if not health_success:
            print("⚠️ Health check failed, but continuing with MCP test...")
        
        # Test 2: The CRITICAL test - exact Claude.ai MCP request format with retries
        print("🔍 Testing REAL Claude.ai MCP request...")
        
        mcp_request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": "claude-test-001",
            "params": {}
        }
        
        mcp_success = False
        for attempt in range(5):  # More attempts for MCP
            try:
                print(f"🔄 MCP attempt {attempt+1}/5...")
                response = requests.post(
                    tunnel_url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "User-Agent": "Claude.ai/1.0"
                    },
                    json=mcp_request,
                    timeout=30
                )
                
                print(f"🔍 MCP Response Status: {response.status_code}")
                print(f"🔍 MCP Response Headers: {dict(response.headers)}")
                print(f"🔍 MCP Response Body: {response.text[:500]}...")
                
                if response.status_code == 200:
                    # Parse SSE response
                    response_text = response.text.strip()
                    if response_text.startswith("data: "):
                        json_data = response_text.replace("data: ", "").strip()
                        try:
                            mcp_data = json.loads(json_data)
                        except json.JSONDecodeError as e:
                            print(f"❌ JSON decode error: {e}")
                            continue
                    else:
                        try:
                            mcp_data = response.json()
                        except json.JSONDecodeError as e:
                            print(f"❌ JSON decode error: {e}")
                            continue
                    
                    print(f"🔍 Parsed MCP Data: {json.dumps(mcp_data, indent=2)}")
                    
                    # Validate MCP protocol response
                    if "error" in mcp_data:
                        print(f"❌ MCP returned error: {mcp_data['error']}")
                        continue
                    
                    if "result" not in mcp_data:
                        print(f"❌ No result in MCP response: {mcp_data}")
                        continue
                    
                    result = mcp_data["result"]
                    if "tools" not in result:
                        print(f"❌ No tools in MCP result: {result}")
                        continue
                    
                    tools = result["tools"]
                    if len(tools) == 0:
                        print(f"❌ Empty tools list - this is exactly what Claude.ai sees!")
                        continue
                    
                    # Verify claude_code tool exists
                    tool_names = [tool["name"] for tool in tools]
                    if "claude_code" not in tool_names:
                        print(f"❌ claude_code tool missing. Available tools: {tool_names}")
                        continue
                    
                    print(f"✅ SUCCESS: Real E2E test passed!")
                    print(f"✅ Found {len(tools)} tools: {tool_names[:5]}{'...' if len(tool_names) > 5 else ''}")
                    print(f"✅ Tunnel URL: {tunnel_url}")
                    mcp_success = True
                    break
                    
                else:
                    print(f"❌ HTTP {response.status_code}: {response.text[:200]}...")
                    time.sleep(15)  # Wait longer between attempts
                    
            except Exception as e:
                print(f"❌ MCP request error (attempt {attempt+1}): {e}")
                time.sleep(15)
        
        if not mcp_success:
            pytest.fail(f"❌ REAL E2E FAILURE: All MCP attempts failed after 5 tries")
        
        return tunnel_url, tools
        
    finally:
        # Always cleanup
        print("🧹 Cleaning up...")
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("✅ Cleanup complete")


if __name__ == "__main__":
    # Run the test directly
    test_real_vibecode_cli_with_tunnel()