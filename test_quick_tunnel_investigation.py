#!/usr/bin/env python3
"""
Investigation test for vibecode start --quick tunnel issues.
This test will help debug the tunnel connectivity problems.
"""

import subprocess
import sys
import time
import pytest
import requests
import threading
import json
import uuid
from pathlib import Path
import re


def test_quick_tunnel_investigation():
    """Investigate why vibecode start --quick fails to create working tunnel."""
    
    print("\n🔍 Starting investigation of vibecode start --quick tunnel issues")
    
    # 1. First verify cloudflared is available
    print("\n1. Checking cloudflared availability...")
    cloudflared_paths = [
        "cloudflared",
        "/opt/homebrew/bin/cloudflared",
        "/usr/local/bin/cloudflared",
        "/usr/bin/cloudflared",
    ]
    
    cloudflared_cmd = None
    for path in cloudflared_paths:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                cloudflared_cmd = path
                print(f"✅ Found cloudflared at: {path}")
                print(f"   Version: {result.stdout.strip()}")
                break
        except FileNotFoundError:
            continue
    
    if not cloudflared_cmd:
        pytest.skip("cloudflared not found - cannot test tunnel functionality")
    
    # 2. Test basic cloudflared quick tunnel functionality
    print("\n2. Testing cloudflared quick tunnel creation...")
    
    # Start a simple HTTP server first
    simple_server_proc = subprocess.Popen([
        sys.executable, "-c", 
        """
import http.server
import socketserver
import json

class SimpleHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'ok', 'path': self.path}).encode())
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {'status': 'received', 'body_length': content_length}
        self.wfile.write(json.dumps(response).encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logs

with socketserver.TCPServer(("127.0.0.1", 8399), SimpleHandler) as httpd:
    print("Simple server running on port 8399", flush=True)
    httpd.serve_forever()
"""
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    time.sleep(2)  # Let server start
    
    # Test local server works
    try:
        local_response = requests.get("http://127.0.0.1:8399/test", timeout=5)
        print(f"✅ Local server responsive: {local_response.status_code}")
    except Exception as e:
        print(f"❌ Local server not responsive: {e}")
        simple_server_proc.terminate()
        return
    
    # Start cloudflared tunnel
    print("\n3. Starting cloudflared quick tunnel...")
    tunnel_proc = subprocess.Popen([
        cloudflared_cmd, "tunnel", "--no-autoupdate", 
        "--url", "http://127.0.0.1:8399"
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    # Parse cloudflared output to find URL
    tunnel_url = None
    tunnel_errors = []
    url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
    
    start_time = time.time()
    timeout = 60
    
    print("   Waiting for tunnel URL...")
    while time.time() - start_time < timeout:
        line = tunnel_proc.stdout.readline()
        if not line:
            if tunnel_proc.poll() is not None:
                break
            time.sleep(0.1)
            continue
        
        print(f"   [cloudflared] {line.strip()}")
        
        # Check for errors
        if "ERR" in line or "error" in line.lower():
            tunnel_errors.append(line.strip())
        
        # Check for rate limiting
        if "429 Too Many Requests" in line or "Too Many Requests" in line:
            print("⚠️  Rate limiting detected")
            break
        
        # Look for tunnel URL
        if not tunnel_url:
            match = url_pattern.search(line)
            if match:
                tunnel_url = match.group(0)
                print(f"✅ Found tunnel URL: {tunnel_url}")
                break
    
    if not tunnel_url:
        print("❌ Failed to get tunnel URL")
        if tunnel_errors:
            print("   Errors found:")
            for error in tunnel_errors:
                print(f"     {error}")
        tunnel_proc.terminate()
        simple_server_proc.terminate()
        return
    
    # 4. Test tunnel connectivity
    print(f"\n4. Testing tunnel connectivity to {tunnel_url}")
    
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            print(f"   Attempt {attempt + 1}/{max_attempts}...")
            response = requests.get(f"{tunnel_url}/test", timeout=10)
            print(f"✅ Tunnel works! Status: {response.status_code}")
            print(f"   Response: {response.text}")
            break
        except requests.exceptions.ConnectTimeout:
            print(f"   Connection timeout on attempt {attempt + 1}")
            time.sleep(3)
        except requests.exceptions.ReadTimeout:
            print(f"   Read timeout on attempt {attempt + 1}")
            time.sleep(3)
        except Exception as e:
            print(f"   Error on attempt {attempt + 1}: {e}")
            time.sleep(3)
    else:
        print("❌ All tunnel connectivity attempts failed")
        print("\n5. Additional diagnostics...")
        
        # Try with curl to see if it's a Python requests issue
        try:
            curl_result = subprocess.run([
                "curl", "-v", "--connect-timeout", "10", "--max-time", "30",
                f"{tunnel_url}/test"
            ], capture_output=True, text=True, timeout=35)
            print(f"   curl exit code: {curl_result.returncode}")
            print(f"   curl stdout: {curl_result.stdout}")
            print(f"   curl stderr: {curl_result.stderr}")
        except Exception as e:
            print(f"   curl test failed: {e}")
    
    # 5. Now test with actual vibecode server
    print(f"\n6. Testing with actual vibecode server...")
    
    # Stop the simple server
    simple_server_proc.terminate()
    simple_server_proc.wait()
    
    # Stop existing tunnel
    tunnel_proc.terminate()
    tunnel_proc.wait()
    
    # Start vibecode server
    print("   Starting vibecode server...")
    vibecode_proc = subprocess.Popen([
        sys.executable, "-m", "vibecode.cli", "start", 
        "--quick", "--port", "8398"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Wait for startup and capture the URL
    vibecode_url = None
    vibecode_errors = []
    
    for i in range(60):  # Wait up to 60 seconds
        line = vibecode_proc.stdout.readline()
        if line:
            line = line.strip()
            print(f"   [vibecode stdout] {line}")
            # Look for URL pattern in stdout
            if line.startswith("https://") and "trycloudflare.com" in line:
                vibecode_url = line
                break
        
        # Also check stderr
        line = vibecode_proc.stderr.readline()
        if line:
            line = line.strip()
            print(f"   [vibecode stderr] {line}")
            # Look for errors
            if "error" in line.lower() or "failed" in line.lower():
                vibecode_errors.append(line)
    
    if not vibecode_url:
        print("❌ Failed to get vibecode URL")
        if vibecode_errors:
            print("   Errors found:")
            for error in vibecode_errors:
                print(f"     {error}")
    else:
        print(f"✅ Got vibecode URL: {vibecode_url}")
        
        # Test the vibecode tunnel
        print("   Testing vibecode tunnel...")
        try:
            response = requests.get(f"{vibecode_url}/.well-known/oauth-authorization-server", timeout=15)
            print(f"✅ Vibecode tunnel works! Status: {response.status_code}")
            print(f"   OAuth metadata: {response.json()}")
        except Exception as e:
            print(f"❌ Vibecode tunnel test failed: {e}")
    
    # Cleanup
    print("\n7. Cleaning up...")
    try:
        vibecode_proc.terminate()
        vibecode_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        vibecode_proc.kill()
    
    print("✅ Investigation complete")


if __name__ == "__main__":
    test_quick_tunnel_investigation()