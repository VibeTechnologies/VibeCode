"""Test to debug cloudflared connection issues."""

import subprocess
import sys
import time
import threading
import re
import requests
import socket
from pathlib import Path


def test_cloudflared_connection_directly():
    """Test if cloudflared can connect to our server directly."""
    
    print("🔍 DEBUG: Testing cloudflared direct connection...")
    
    # Start server on a known port
    port = 8503
    proc = subprocess.Popen([
        sys.executable, '-m', 'vibecode.cli', 'start', '--no-tunnel', '--port', str(port)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    
    server_ready = False
    uuid_path = None
    
    def read_server_output():
        nonlocal server_ready, uuid_path
        try:
            for line in iter(proc.stderr.readline, ''):
                print(f"SERVER: {line.strip()}")
                if 'Server is ready on port' in line:
                    server_ready = True
                if 'MCP endpoint ready at' in line:
                    uuid_match = re.search(r'/([a-f0-9]{32})', line)
                    if uuid_match:
                        uuid_path = uuid_match.group(1)
        except Exception as e:
            print(f"❌ Error reading server output: {e}")
    
    output_thread = threading.Thread(target=read_server_output, daemon=True)
    output_thread.start()
    
    # Wait for server to start
    for i in range(30):
        if server_ready and uuid_path:
            break
        time.sleep(1)
    
    if not server_ready or not uuid_path:
        proc.terminate()
        raise Exception("Server failed to start")
    
    print(f"✅ Server ready on port {port} with UUID path: /{uuid_path}")
    
    try:
        # Test 1: Verify local connectivity
        print("\n1. Testing local connectivity...")
        time.sleep(2)  # Give server time to fully initialize
        
        test_urls = [
            f"http://127.0.0.1:{port}/health",
            f"http://127.0.0.1:{port}/{uuid_path}",
            f"http://localhost:{port}/health",
            f"http://localhost:{port}/{uuid_path}"
        ]
        
        for url in test_urls:
            try:
                response = requests.get(url, timeout=5)
                print(f"   {url}: {response.status_code}")
            except Exception as e:
                print(f"   {url}: ERROR - {e}")
        
        # Test 2: Check if the port is actually listening
        print(f"\n2. Testing port binding...")
        for host in ['127.0.0.1', 'localhost']:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2)
                    result = s.connect_ex((host, port))
                    if result == 0:
                        print(f"   ✅ Port {port} is listening on {host}")
                    else:
                        print(f"   ❌ Port {port} is NOT listening on {host}")
            except Exception as e:
                print(f"   ❌ Cannot test {host}:{port} - {e}")
        
        # Test 3: Start cloudflared manually and see what happens
        print(f"\n3. Testing cloudflared manually...")
        
        # Find cloudflared
        cloudflared_cmd = None
        for path in ["cloudflared", "/opt/homebrew/bin/cloudflared", "/usr/local/bin/cloudflared", "/usr/bin/cloudflared"]:
            try:
                subprocess.run([path, "--version"], capture_output=True, check=True)
                cloudflared_cmd = path
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        if not cloudflared_cmd:
            print("   ❌ cloudflared not found")
            return
        
        print(f"   Found cloudflared: {cloudflared_cmd}")
        
        # Start cloudflared manually
        base_url = f"http://127.0.0.1:{port}"
        print(f"   Starting cloudflared with URL: {base_url}")
        
        cloudflared_proc = subprocess.Popen(
            [cloudflared_cmd, "tunnel", "--no-autoupdate", "--url", base_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        tunnel_url = None
        cloudflared_ready = False
        
        def read_cloudflared_output():
            nonlocal tunnel_url, cloudflared_ready
            try:
                for line in iter(cloudflared_proc.stdout.readline, ''):
                    print(f"CLOUDFLARED: {line.strip()}")
                    
                    if "trycloudflare.com" in line and "https://" in line:
                        url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
                        if url_match:
                            tunnel_url = url_match.group(0)
                            cloudflared_ready = True
                            print(f"✅ Cloudflared tunnel ready: {tunnel_url}")
                            break
                    
                    # Look for error messages
                    if "ERR" in line.upper() or "ERRO" in line.upper():
                        print(f"❌ Cloudflared error: {line.strip()}")
                        
            except Exception as e:
                print(f"❌ Error reading cloudflared output: {e}")
        
        cloudflared_output_thread = threading.Thread(target=read_cloudflared_output, daemon=True)
        cloudflared_output_thread.start()
        
        # Wait for cloudflared to start
        for i in range(60):
            if cloudflared_ready and tunnel_url:
                break
            time.sleep(1)
        
        if tunnel_url:
            print(f"\n4. Testing tunnel connectivity...")
            time.sleep(30)  # Wait for tunnel to propagate
            
            test_tunnel_urls = [
                f"{tunnel_url}/",
                f"{tunnel_url}/health",
                f"{tunnel_url}/{uuid_path}"
            ]
            
            for url in test_tunnel_urls:
                try:
                    print(f"   Testing: {url}")
                    response = requests.get(url, timeout=30)
                    print(f"   Status: {response.status_code}")
                    if response.status_code == 530:
                        print(f"   ❌ 530 Error - Cloudflared cannot connect to local server")
                    elif response.status_code == 200:
                        print(f"   ✅ Success!")
                    else:
                        print(f"   Response: {response.text[:100]}...")
                except Exception as e:
                    print(f"   ERROR: {e}")
        else:
            print("   ❌ Could not get tunnel URL from cloudflared")
        
        cloudflared_proc.terminate()
        cloudflared_proc.wait()
        
    finally:
        proc.terminate()
        proc.wait()
        print("\n🧹 Cleanup complete")


if __name__ == "__main__":
    test_cloudflared_connection_directly()