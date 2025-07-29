"""Debug test to investigate tunnel connectivity issues."""

import subprocess
import sys
import time
import threading
import re
import requests
import json
from pathlib import Path
import pytest


def test_debug_tunnel_connectivity():
    """Debug test to investigate why tunnels return 530 errors."""
    
    print("🔍 DEBUG: Starting tunnel connectivity investigation...")
    
    # Test 1: Can we start the server locally without tunnels?
    print("\n1. Testing local server startup...")
    
    proc = subprocess.Popen([
        sys.executable, '-m', 'vibecode.cli', 'start', '--no-tunnel', '--port', '8501'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    
    uuid_path = None
    server_ready = False
    
    def read_local_output():
        nonlocal uuid_path, server_ready
        try:
            for line in iter(proc.stderr.readline, ''):
                print(f"LOCAL SERVER: {line.strip()}")
                if 'MCP endpoint ready at' in line:
                    uuid_match = re.search(r'/([a-f0-9]{32})', line)
                    if uuid_match:
                        uuid_path = uuid_match.group(1)
                        print(f"🔗 Found UUID path: /{uuid_path}")
                        
                if 'Server is ready on port' in line:
                    server_ready = True
                    print("✅ Local server is ready")
                    break
        except Exception as e:
            print(f"❌ Error reading local output: {e}")
    
    output_thread = threading.Thread(target=read_local_output, daemon=True)
    output_thread.start()
    
    # Wait for local server to start
    for i in range(30):
        if server_ready and uuid_path:
            break
        time.sleep(1)
    
    if not server_ready or not uuid_path:
        proc.terminate()
        pytest.fail("❌ Local server failed to start properly")
    
    try:
        # Test local connectivity
        local_url = f"http://127.0.0.1:8501/{uuid_path}"
        print(f"\n2. Testing local connectivity to: {local_url}")
        
        time.sleep(2)  # Give server time to fully initialize
        
        # Test health endpoint
        try:
            health_response = requests.get("http://127.0.0.1:8501/health", timeout=10)
            print(f"   Health endpoint: {health_response.status_code}")
        except Exception as e:
            print(f"   Health endpoint failed: {e}")
        
        # Test MCP endpoint
        try:
            mcp_response = requests.post(
                local_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                },
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "id": "local-test",
                    "params": {}
                },
                timeout=10
            )
            print(f"   MCP endpoint: {mcp_response.status_code}")
            if mcp_response.status_code == 200:
                print("✅ Local MCP endpoint works correctly")
            else:
                print(f"❌ Local MCP endpoint failed: {mcp_response.text[:200]}")
        except Exception as e:
            print(f"   MCP endpoint failed: {e}")
        
        print("\n3. Now testing with tunnel...")
        
        # Now test with tunnel - start a separate process
        tunnel_proc = subprocess.Popen([
            sys.executable, '-m', 'vibecode.cli', 'start', '--quick', '--port', '8502'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        
        tunnel_url = None
        tunnel_uuid_path = None
        tunnel_ready = False
        
        def read_tunnel_output():
            nonlocal tunnel_url, tunnel_uuid_path, tunnel_ready
            base_tunnel_url = None
            
            try:
                for line in iter(tunnel_proc.stderr.readline, ''):
                    print(f"TUNNEL SERVER: {line.strip()}")
                    
                    if 'trycloudflare.com' in line and 'https://' in line:
                        url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
                        if url_match:
                            base_tunnel_url = url_match.group(0)
                            print(f"🔗 Found tunnel base URL: {base_tunnel_url}")
                    
                    if 'MCP endpoint ready at' in line:
                        uuid_match = re.search(r'/([a-f0-9]{32})', line)
                        if uuid_match:
                            tunnel_uuid_path = uuid_match.group(1)
                            if base_tunnel_url:
                                tunnel_url = f"{base_tunnel_url}/{tunnel_uuid_path}"
                                print(f"🔗 Complete tunnel URL: {tunnel_url}")
                                tunnel_ready = True
                                break
                    
                    # Also look for complete URLs printed together
                    complete_url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com/[a-f0-9]{32}', line)
                    if complete_url_match:
                        tunnel_url = complete_url_match.group(0)
                        tunnel_ready = True
                        print(f"🔗 Found complete tunnel URL: {tunnel_url}")
                        break
            except Exception as e:
                print(f"❌ Error reading tunnel output: {e}")
        
        tunnel_output_thread = threading.Thread(target=read_tunnel_output, daemon=True)
        tunnel_output_thread.start()
        
        # Wait for tunnel to be established
        for i in range(60):
            if tunnel_ready and tunnel_url:
                break
            time.sleep(1)
            if i % 10 == 0:
                print(f"⏳ Still waiting for tunnel... ({i}s)")
        
        if not tunnel_ready or not tunnel_url:
            tunnel_proc.terminate()
            pytest.fail("❌ Tunnel failed to start properly")
        
        # Test tunnel connectivity with detailed debugging
        print(f"\n4. Testing tunnel connectivity to: {tunnel_url}")
        print("   Waiting for tunnel to propagate...")
        time.sleep(45)  # Wait longer for tunnel to propagate
        
        # Test various endpoints through the tunnel
        base_tunnel_url = tunnel_url.split('/' + tunnel_uuid_path)[0]
        
        test_endpoints = [
            ("Base tunnel", f"{base_tunnel_url}/"),
            ("Health endpoint", f"{base_tunnel_url}/health"),
            ("MCP endpoint", tunnel_url)
        ]
        
        for name, url in test_endpoints:
            try:
                print(f"\n   Testing {name}: {url}")
                response = requests.get(url, timeout=30)
                print(f"   Status: {response.status_code}")
                print(f"   Headers: {dict(response.headers)}")
                if response.status_code == 530:
                    print(f"   Body (530 error): {response.text[:200]}...")
                elif response.status_code == 200:
                    print(f"   Body: {response.text[:100]}...")
                else:
                    print(f"   Body: {response.text[:100]}...")
            except Exception as e:
                print(f"   Error: {e}")
        
        # Try MCP request through tunnel
        if tunnel_url:
            print(f"\n5. Testing MCP protocol through tunnel...")
            try:
                mcp_response = requests.post(
                    tunnel_url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    },
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": "tunnel-test",
                        "params": {}
                    },
                    timeout=30
                )
                print(f"   MCP Response Status: {mcp_response.status_code}")
                if mcp_response.status_code == 200:
                    print("✅ MCP through tunnel works!")
                else:
                    print(f"❌ MCP through tunnel failed: {mcp_response.text[:200]}")
            except Exception as e:
                print(f"   MCP through tunnel error: {e}")
        
        tunnel_proc.terminate()
        tunnel_proc.wait()
        
    finally:
        proc.terminate()
        proc.wait()
        print("\n🧹 Cleanup complete")


if __name__ == "__main__":
    test_debug_tunnel_connectivity()