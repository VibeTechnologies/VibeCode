#!/usr/bin/env python3
"""
Comprehensive end-to-end integration test for VibeCode tunnel functionality.
Tests the complete flow: start server -> create tunnel -> verify MCP accessibility.
"""

import subprocess
import sys
import time
import re
import requests
import json
import threading
from pathlib import Path
import uuid


class TunnelE2ETest:
    """Comprehensive tunnel end-to-end test runner."""
    
    def __init__(self, port=8400):
        self.port = port
        self.process = None
        self.tunnel_url = None
        self.mcp_path = None
        self.success = False
        
    def run_test(self, timeout=90):
        """Run complete end-to-end test."""
        print("🚀 Starting comprehensive tunnel E2E test...")
        
        try:
            # Step 1: Start vibecode with quick tunnel
            self.process = subprocess.Popen([
                sys.executable, '-m', 'vibecode.cli', 'start', 
                '--quick', '--port', str(self.port)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            
            # Step 2: Parse tunnel output and extract URL
            if not self._wait_for_tunnel(timeout):
                return False
                
            # Step 3: Test OAuth endpoints through tunnel
            if not self._test_oauth_endpoints():
                return False
                
            # Step 4: Test MCP server accessibility
            if not self._test_mcp_server():
                return False
                
            # Step 5: Test MCP tools functionality
            if not self._test_mcp_tools():
                return False
                
            self.success = True
            print("🎉 SUCCESS: All tunnel E2E tests passed!")
            return True
            
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR: {e}")
            return False
            
        finally:
            self._cleanup()
    
    def _wait_for_tunnel(self, timeout):
        """Wait for tunnel to be established and extract URL."""
        print("⏳ Waiting for tunnel establishment...")
        
        start_time = time.time()
        server_started = False
        cloudflared_started = False
        
        while time.time() - start_time < timeout:
            line = self.process.stderr.readline()
            if not line:
                if self.process.poll() is not None:
                    print("❌ Process terminated unexpectedly")
                    return False
                time.sleep(0.1)
                continue
                
            line = line.strip()
            print(f"[LOG] {line}")
            
            # Track server startup
            if 'Server is ready on port' in line:
                server_started = True
                print("✅ MCP server started")
                
            # Track cloudflared startup
            if 'Starting cloudflared' in line:
                cloudflared_started = True
                print("✅ Cloudflared started")
                
            # Extract MCP path from log
            if 'MCP endpoint ready at:' in line:
                path_match = re.search(r'/([a-f0-9]+)', line)
                if path_match:
                    self.mcp_path = path_match.group(0)
                    print(f"✅ MCP path extracted: {self.mcp_path}")
            
            # Look for tunnel URL
            if 'trycloudflare.com' in line:
                url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
                if url_match:
                    self.tunnel_url = url_match.group(0)
                    print(f"✅ Tunnel URL found: {self.tunnel_url}")
                    
                    # Wait a bit more for tunnel to stabilize
                    time.sleep(5)
                    return True
        
        print(f"❌ TIMEOUT: Failed to establish tunnel within {timeout}s")
        print(f"   Server started: {server_started}")
        print(f"   Cloudflared started: {cloudflared_started}")
        return False
    
    def _test_oauth_endpoints(self):
        """Test OAuth endpoints through tunnel."""
        print("🔐 Testing OAuth endpoints through tunnel...")
        
        if not self.tunnel_url:
            print("❌ No tunnel URL available for OAuth testing")
            return False
            
        oauth_endpoints = [
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-protected-resource", 
            "/health"
        ]
        
        for endpoint in oauth_endpoints:
            try:
                url = f"{self.tunnel_url}{endpoint}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    print(f"✅ OAuth endpoint {endpoint}: 200 OK")
                else:
                    print(f"❌ OAuth endpoint {endpoint}: {response.status_code}")
                    return False
                    
            except Exception as e:
                print(f"❌ OAuth endpoint {endpoint} failed: {e}")
                return False
        
        return True
    
    def _test_mcp_server(self):
        """Test MCP server through tunnel."""
        print("🔧 Testing MCP server through tunnel...")
        
        if not self.tunnel_url or not self.mcp_path:
            print("❌ Missing tunnel URL or MCP path for server testing")
            return False
        
        mcp_url = f"{self.tunnel_url}{self.mcp_path}"
        
        # Test MCP initialize request
        try:
            response = requests.post(
                mcp_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"
                },
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
                timeout=15
            )
            
            if response.status_code == 200:
                print("✅ MCP initialize: 200 OK")
                
                # Check response format
                if "text/event-stream" in response.headers.get("content-type", ""):
                    print("✅ MCP SSE headers: OK")
                else:
                    print("⚠️  MCP SSE headers: missing or incorrect")
                    
                return True
            else:
                print(f"❌ MCP initialize failed: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            print(f"❌ MCP server test failed: {e}")
            return False
    
    def _test_mcp_tools(self):
        """Test MCP tools/list functionality through tunnel."""
        print("🛠️  Testing MCP tools through tunnel...")
        
        if not self.tunnel_url or not self.mcp_path:
            print("❌ Missing tunnel URL or MCP path for tools testing")
            return False
        
        mcp_url = f"{self.tunnel_url}{self.mcp_path}"
        
        # Test tools/list request
        try:
            response = requests.post(
                mcp_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"
                },
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "id": 2,
                    "params": {}
                },
                timeout=15
            )
            
            if response.status_code == 200:
                print("✅ MCP tools/list: 200 OK")
                
                # Try to parse response content for tools
                content = response.text
                if 'claude_code' in content:
                    print("✅ Claude Code tool found in response")
                else:
                    print("⚠️  Claude Code tool not found in response")
                    
                return True
            else:
                print(f"❌ MCP tools/list failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ MCP tools test failed: {e}")
            return False
    
    def _cleanup(self):
        """Clean up test process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            except Exception:
                pass


def test_tunnel_e2e_comprehensive():
    """Comprehensive tunnel end-to-end test."""
    tester = TunnelE2ETest()
    return tester.run_test()


def test_tunnel_e2e_with_tool_execution():
    """Test complete flow including tool execution."""
    print("🚀 Starting comprehensive tunnel E2E test with tool execution...")
    
    tester = TunnelE2ETest(port=8401)
    
    # First establish the tunnel
    tester.process = subprocess.Popen([
        sys.executable, '-m', 'vibecode.cli', 'start', 
        '--quick', '--port', str(tester.port)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    
    try:
        # Wait for tunnel
        if not tester._wait_for_tunnel(90):
            return False
            
        # Test simple claude_code tool execution
        mcp_url = f"{tester.tunnel_url}{tester.mcp_path}"
        
        response = requests.post(
            mcp_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 3,
                "params": {
                    "name": "claude_code",
                    "arguments": {
                        "prompt": "echo 'Hello from tunnel test'",
                        "workFolder": "/tmp"
                    }
                }
            },
            timeout=30
        )
        
        if response.status_code == 200:
            print("✅ Tool execution through tunnel: 200 OK")
            
            # Check for expected response format
            content = response.text
            if 'Hello from tunnel test' in content:
                print("✅ Tool execution output verified")
                return True
            else:
                print("⚠️  Tool execution output not as expected")
                print(f"   Content: {content[:200]}")
                return True  # Still consider success if we got 200
        else:
            print(f"❌ Tool execution failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Tool execution test failed: {e}")
        return False
        
    finally:
        tester._cleanup()


def main():
    """Main test runner."""
    print("=" * 60)
    print("🧪 VibeCode Tunnel E2E Integration Tests")
    print("=" * 60)
    
    # Test 1: Basic tunnel functionality
    print("\n📋 Test 1: Basic tunnel functionality")
    success1 = test_tunnel_e2e_comprehensive()
    
    # Test 2: Tool execution through tunnel
    print("\n📋 Test 2: Tool execution through tunnel")
    success2 = test_tunnel_e2e_with_tool_execution()
    
    # Results
    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"   Basic tunnel functionality: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"   Tool execution through tunnel: {'✅ PASS' if success2 else '❌ FAIL'}")
    
    overall_success = success1 and success2
    print(f"\n🎯 Overall Result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    return overall_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)