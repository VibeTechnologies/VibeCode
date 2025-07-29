"""Test the HTTP2 protocol fix for cloudflared connectivity issues."""

import subprocess
import sys
import time
import threading
import re
import requests
import json


def test_http2_fix():
    """Test if the HTTP2 protocol fix resolves the QUIC connection issues."""
    
    print("🔍 Testing HTTP2 protocol fix for cloudflared...")
    
    # Test with quick tunnel using the fixed CLI
    proc = subprocess.Popen([
        sys.executable, '-m', 'vibecode.cli', 'start', '--quick', '--port', '8505'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    
    tunnel_url = None
    uuid_path = None
    server_ready = False
    
    def read_output():
        nonlocal tunnel_url, uuid_path, server_ready
        base_tunnel_url = None
        
        try:
            for line in iter(proc.stderr.readline, ''):
                print(f"OUTPUT: {line.strip()}")
                
                # Check for server ready
                if 'Server is ready on port' in line:
                    server_ready = True
                
                # Look for tunnel URL
                if 'trycloudflare.com' in line and 'https://' in line:
                    url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
                    if url_match:
                        base_tunnel_url = url_match.group(0)
                        print(f"🔗 Found tunnel base URL: {base_tunnel_url}")
                
                # Look for UUID path  
                if 'MCP endpoint ready at' in line:
                    uuid_match = re.search(r'/([a-f0-9]{32})', line)
                    if uuid_match:
                        uuid_path = uuid_match.group(1)
                        if base_tunnel_url:
                            tunnel_url = f"{base_tunnel_url}/{uuid_path}"
                            print(f"🔗 Complete tunnel URL: {tunnel_url}")
                            break
                
                # Also look for complete URLs printed together
                complete_url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com/[a-f0-9]{32}', line)
                if complete_url_match:
                    tunnel_url = complete_url_match.group(0)
                    print(f"🔗 Found complete tunnel URL: {tunnel_url}")
                    break
                        
        except Exception as e:
            print(f"❌ Error reading output: {e}")
    
    output_thread = threading.Thread(target=read_output, daemon=True)
    output_thread.start()
    
    try:
        # Wait for tunnel to be established
        print("⏳ Waiting for tunnel to be established...")
        for i in range(90):  # Increased timeout
            if tunnel_url and server_ready:
                break
            time.sleep(1)
            if i % 15 == 0:
                print(f"⏳ Still waiting... ({i}s)")
        
        if not tunnel_url:
            print("❌ FAILED: Could not extract tunnel URL from CLI output")
            return False
        
        print(f"✅ Tunnel established: {tunnel_url}")
        
        # Wait for tunnel to be fully ready (HTTP2 should be faster than QUIC)
        print("⏳ Waiting for tunnel to become accessible...")
        time.sleep(45)  # Still need time for tunnel propagation
        
        # Test health endpoint first
        print("🔍 Testing health endpoint...")
        base_tunnel_url = tunnel_url.split('/' + uuid_path)[0]
        
        try:
            health_response = requests.get(f"{base_tunnel_url}/health", timeout=20)
            print(f"Health response: {health_response.status_code}")
            if health_response.status_code == 200:
                print("✅ Health endpoint works!")
            elif health_response.status_code == 530:
                print("❌ Still getting 530 errors - HTTP2 fix didn't work")
                return False
            else:
                print(f"⚠️ Unexpected health response: {health_response.status_code}")
        except Exception as e:
            print(f"⚠️ Health check failed: {e}")
        
        # Test MCP endpoint
        print("🔍 Testing MCP endpoint...")
        
        mcp_request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": "http2-test",
            "params": {}
        }
        
        try:
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
            
            if response.status_code == 200:
                # Parse SSE response
                response_text = response.text.strip()
                if response_text.startswith("data: "):
                    json_data = response_text.replace("data: ", "").strip()
                    try:
                        mcp_data = json.loads(json_data)
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON decode error: {e}")
                        return False
                else:
                    try:
                        mcp_data = response.json()
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON decode error: {e}")
                        return False
                
                # Validate MCP protocol response
                if "error" in mcp_data:
                    print(f"❌ MCP returned error: {mcp_data['error']}")
                    return False
                
                if "result" not in mcp_data:
                    print(f"❌ No result in MCP response: {mcp_data}")
                    return False
                
                result = mcp_data["result"]
                if "tools" not in result:
                    print(f"❌ No tools in MCP result: {result}")
                    return False
                
                tools = result["tools"]
                if len(tools) == 0:
                    print(f"❌ Empty tools list")
                    return False
                
                tool_names = [tool["name"] for tool in tools]
                if "claude_code" not in tool_names:
                    print(f"❌ claude_code tool missing. Available tools: {tool_names}")
                    return False
                
                print(f"✅ SUCCESS: HTTP2 fix worked!")
                print(f"✅ Found {len(tools)} tools: {tool_names[:5]}{'...' if len(tool_names) > 5 else ''}")
                print(f"✅ Tunnel URL: {tunnel_url}")
                return True
                
            elif response.status_code == 530:
                print(f"❌ Still getting 530 errors - HTTP2 fix didn't resolve the issue")
                return False
            else:
                print(f"❌ HTTP {response.status_code}: {response.text[:200]}...")
                return False
                
        except Exception as e:
            print(f"❌ MCP request error: {e}")
            return False
        
    finally:
        print("🧹 Cleaning up...")
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("✅ Cleanup complete")


if __name__ == "__main__":
    success = test_http2_fix()
    if success:
        print("\n🎉 HTTP2 fix successful!")
        sys.exit(0)
    else:
        print("\n❌ HTTP2 fix failed")
        sys.exit(1)