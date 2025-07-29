"""Test if cloudflared can connect to a simple HTTP server."""

import subprocess
import sys
import time
import threading
import re
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import json


class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        print(f"SIMPLE SERVER: Received GET {self.path}")
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"message": "Hello from simple server", "path": self.path}
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        print(f"SIMPLE SERVER: Received POST {self.path}")
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else ""
        print(f"SIMPLE SERVER: POST body: {body[:100]}...")
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"message": "Hello from simple server POST", "path": self.path, "received_body": body[:50]}
        self.wfile.write(json.dumps(response).encode())
    
    def log_message(self, format, *args):
        # Suppress default logging - we'll do our own
        pass


def test_simple_http_server():
    """Test if cloudflared can connect to a simple Python HTTP server."""
    
    print("🔍 Testing cloudflared with simple HTTP server...")
    
    # Start simple HTTP server
    port = 8507
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    
    def run_server():
        print(f"✅ Simple HTTP server running on 0.0.0.0:{port}")
        server.serve_forever()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Give server time to start
    time.sleep(2)
    
    # Test local connectivity first
    print("\n1. Testing local connectivity...")
    try:
        response = requests.get(f"http://127.0.0.1:{port}/test", timeout=5)
        print(f"   Local test: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"   Local test failed: {e}")
        return False
    
    # Start cloudflared
    print(f"\n2. Starting cloudflared...")
    
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
        return False
    
    base_url = f"http://127.0.0.1:{port}"
    print(f"   Starting cloudflared with URL: {base_url}")
    
    cloudflared_proc = subprocess.Popen(
        [cloudflared_cmd, "tunnel", "--no-autoupdate", "--protocol", "h2mux", "--url", base_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    tunnel_url = None
    
    def read_cloudflared_output():
        nonlocal tunnel_url
        try:
            for line in iter(cloudflared_proc.stdout.readline, ''):
                print(f"CLOUDFLARED: {line.strip()}")
                
                if "trycloudflare.com" in line and "https://" in line:
                    url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
                    if url_match:
                        tunnel_url = url_match.group(0)
                        print(f"✅ Tunnel URL: {tunnel_url}")
                        break
        except Exception as e:
            print(f"❌ Error reading cloudflared output: {e}")
    
    cloudflared_output_thread = threading.Thread(target=read_cloudflared_output, daemon=True)
    cloudflared_output_thread.start()
    
    # Wait for tunnel
    for i in range(60):
        if tunnel_url:
            break
        time.sleep(1)
    
    if not tunnel_url:
        print("   ❌ Could not get tunnel URL")
        cloudflared_proc.terminate()
        server.shutdown()
        return False
    
    # Test tunnel connectivity
    print(f"\n3. Testing tunnel connectivity...")
    time.sleep(30)  # Wait for tunnel propagation
    
    test_urls = [
        f"{tunnel_url}/",
        f"{tunnel_url}/test",
        f"{tunnel_url}/health"
    ]
    
    success = False
    for url in test_urls:
        try:
            print(f"   Testing GET {url}")
            response = requests.get(url, timeout=20)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   ✅ Success: {data}")
                    success = True
                except:
                    print(f"   ✅ Success: {response.text[:100]}...")
                    success = True
            elif response.status_code == 502:
                print(f"   ❌ Bad Gateway - cloudflared can't connect to simple server")
            else:
                print(f"   ⚠️ Unexpected: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Request failed: {e}")
    
    # Test POST request
    try:
        print(f"   Testing POST {tunnel_url}/api")
        response = requests.post(
            f"{tunnel_url}/api",
            json={"test": "data"},
            timeout=20
        )
        print(f"   POST Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ POST Success: {response.json()}")
    except Exception as e:
        print(f"   ❌ POST failed: {e}")
    
    cloudflared_proc.terminate()
    cloudflared_proc.wait()
    server.shutdown()
    
    return success


if __name__ == "__main__":
    success = test_simple_http_server()
    if success:
        print("\n🎉 Simple HTTP server tunnel test successful!")
        sys.exit(0)
    else:
        print("\n❌ Simple HTTP server tunnel test failed")
        sys.exit(1)