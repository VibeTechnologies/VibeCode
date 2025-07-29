"""Test with detailed cloudflared logging to understand connection failures."""

import subprocess
import sys
import time
import threading
import re
import requests
import socket
from pathlib import Path


def test_detailed_cloudflared_logs():
    """Test cloudflared with verbose logging to understand connection failures."""
    
    print("🔍 DEBUG: Testing cloudflared with detailed logging...")
    
    # Start server on a known port
    port = 8504
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
        # Give server extra time to fully initialize
        print("⏳ Waiting for server to fully initialize...")
        time.sleep(5)
        
        # Test local connectivity one more time
        print("\n1. Final local connectivity test...")
        try:
            response = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
            print(f"   Local health check: {response.status_code}")
        except Exception as e:
            print(f"   Local health check failed: {e}")
            return
        
        # Start cloudflared with verbose logging
        print(f"\n2. Starting cloudflared with verbose logging...")
        
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
        
        base_url = f"http://127.0.0.1:{port}"
        print(f"   Starting cloudflared with URL: {base_url}")
        
        # Add verbose logging flags
        cloudflared_proc = subprocess.Popen(
            [cloudflared_cmd, "tunnel", "--no-autoupdate", "--url", base_url, "--loglevel", "debug"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        tunnel_url = None
        cloudflared_ready = False
        connection_errors = []
        
        def read_cloudflared_output():
            nonlocal tunnel_url, cloudflared_ready, connection_errors
            try:
                for line in iter(cloudflared_proc.stdout.readline, ''):
                    line_stripped = line.strip()
                    print(f"CLOUDFLARED: {line_stripped}")
                    
                    # Capture connection errors
                    if any(keyword in line_stripped.upper() for keyword in 
                           ['ERROR', 'ERR', 'FAILED', 'REFUSED', 'TIMEOUT', 'UNABLE']):
                        connection_errors.append(line_stripped)
                    
                    # Look for specific connection issues
                    if "connection refused" in line_stripped.lower():
                        print(f"❌ CONNECTION REFUSED: {line_stripped}")
                    elif "dial tcp" in line_stripped.lower() and "refused" in line_stripped.lower():
                        print(f"❌ TCP CONNECTION REFUSED: {line_stripped}")
                    elif "502" in line_stripped or "504" in line_stripped:
                        print(f"❌ GATEWAY ERROR: {line_stripped}")
                    
                    if "trycloudflare.com" in line and "https://" in line:
                        url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
                        if url_match:
                            tunnel_url = url_match.group(0)
                            cloudflared_ready = True
                            print(f"✅ Cloudflared tunnel ready: {tunnel_url}")
                            # Don't break - keep reading for error messages
                            
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
            print(f"\n3. Analyzing connection errors...")
            if connection_errors:
                print("   Connection errors found:")
                for error in connection_errors[-5:]:  # Show last 5 errors
                    print(f"   - {error}")
            else:
                print("   No obvious connection errors in logs")
            
            print(f"\n4. Testing tunnel connectivity...")
            time.sleep(20)  # Shorter wait to see faster results
            
            try:
                print(f"   Testing: {tunnel_url}/health")
                response = requests.get(f"{tunnel_url}/health", timeout=15)
                print(f"   Status: {response.status_code}")
                if response.status_code == 530:
                    print(f"   ❌ 530 Error - This confirms cloudflared cannot reach our server")
                    print(f"   ❌ Server is running and accessible locally, but cloudflared can't connect")
                elif response.status_code == 200:
                    print(f"   ✅ Success! Tunnel is working")
                    response_content = response.text[:200]
                    print(f"   Response: {response_content}")
            except Exception as e:
                print(f"   Tunnel test error: {e}")
        else:
            print("   ❌ Could not get tunnel URL from cloudflared")
        
        # Keep cloudflared running a bit longer to see ongoing logs
        print(f"\n5. Monitoring cloudflared for 30 more seconds...")
        time.sleep(30)
        
        cloudflared_proc.terminate()
        cloudflared_proc.wait()
        
    finally:
        proc.terminate()
        proc.wait()
        print("\n🧹 Cleanup complete")


if __name__ == "__main__":
    test_detailed_cloudflared_logs()