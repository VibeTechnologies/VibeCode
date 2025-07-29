"""Debug test to see what requests the server is actually receiving through the tunnel."""

import subprocess
import sys
import time
import threading
import re
import requests
import json


def test_server_debug_with_tunnel():
    """Test what requests the server receives through cloudflared tunnel."""
    
    print("🔍 Debugging server requests through tunnel...")
    
    # Start server with more verbose logging
    proc = subprocess.Popen([
        sys.executable, '-m', 'vibecode.cli', 'start', '--quick', '--port', '8506'
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
                
                # Look for UUID path  
                if 'MCP endpoint ready at' in line:
                    uuid_match = re.search(r'/([a-f0-9]{32})', line)
                    if uuid_match:
                        uuid_path = uuid_match.group(1)
                        if base_tunnel_url:
                            tunnel_url = f"{base_tunnel_url}/{uuid_path}"
                            break
                
                # Also look for complete URLs
                complete_url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com/[a-f0-9]{32}', line)
                if complete_url_match:
                    tunnel_url = complete_url_match.group(0)
                    break
                        
        except Exception as e:
            print(f"❌ Error reading output: {e}")
    
    output_thread = threading.Thread(target=read_output, daemon=True)
    output_thread.start()
    
    try:
        # Wait for tunnel to be established
        for i in range(90):
            if tunnel_url and server_ready:
                break
            time.sleep(1)
        
        if not tunnel_url:
            print("❌ Could not get tunnel URL")
            return
        
        print(f"✅ Tunnel URL: {tunnel_url}")
        
        # Wait for tunnel to propagate
        time.sleep(30)
        
        # Test different request types to see server responses
        base_tunnel_url = tunnel_url.split('/' + uuid_path)[0]
        
        test_requests = [
            ("GET /", f"{base_tunnel_url}/"),
            ("GET /health", f"{base_tunnel_url}/health"),
            ("GET MCP endpoint", tunnel_url),
            ("POST MCP endpoint", tunnel_url, {
                "jsonrpc": "2.0",
                "method": "tools/list", 
                "id": "debug-test",
                "params": {}
            })
        ]
        
        for test_name, url, *payload in test_requests:
            print(f"\n🔍 Testing {test_name}: {url}")
            try:
                if payload:
                    # POST request
                    response = requests.post(
                        url,
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json, text/event-stream",
                            "User-Agent": "VibecodeDebug/1.0"
                        },
                        json=payload[0],
                        timeout=20
                    )
                else:
                    # GET request
                    response = requests.get(
                        url,
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "VibecodeDebug/1.0"
                        },
                        timeout=20
                    )
                
                print(f"   Status: {response.status_code}")
                print(f"   Headers: {dict(response.headers)}")
                
                if response.status_code in [200, 201]:
                    print(f"   ✅ Success: {response.text[:100]}...")
                elif response.status_code == 405:
                    print(f"   ⚠️ Method not allowed (expected for GET on POST endpoint)")
                elif response.status_code == 502:
                    print(f"   ❌ Bad Gateway: {response.text[:200]}...")
                elif response.status_code == 530:
                    print(f"   ❌ Site offline: {response.text[:200]}...")
                else:
                    print(f"   ⚠️ Unexpected: {response.text[:100]}...")
                    
            except Exception as e:
                print(f"   ❌ Request failed: {e}")
        
        # Give some time to see any server logs from these requests
        print(f"\n⏳ Waiting for server logs...")
        time.sleep(5)
        
    finally:
        print("🧹 Cleaning up...")
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    test_server_debug_with_tunnel()