#!/usr/bin/env python3
"""
Focused test to diagnose and fix server startup issues.
"""

import subprocess
import sys
import time
import socket
import threading
import json
from pathlib import Path


def test_server_startup_diagnosis():
    """Diagnose server startup issues with detailed monitoring."""
    print("🔍 DIAGNOSING SERVER STARTUP ISSUES")
    print("=" * 50)
    
    # Test 1: Direct MCP server import
    print("1️⃣ Testing direct MCP server import...")
    try:
        from vibecode.server import AuthenticatedMCPServer
        print("✅ AuthenticatedMCPServer import successful")
    except Exception as e:
        print(f"❌ AuthenticatedMCPServer import failed: {e}")
        return False
    
    # Test 2: Basic server creation
    print("\n2️⃣ Testing basic server creation...")
    try:
        server = AuthenticatedMCPServer(
            name="test-server",
            allowed_paths=["/"],
            enable_agent_tool=False,
            base_url="http://localhost:8600"
        )
        print("✅ Server object creation successful")
    except Exception as e:
        print(f"❌ Server creation failed: {e}")
        return False
    
    # Test 3: CLI module import
    print("\n3️⃣ Testing CLI module...")
    try:
        import vibecode.cli
        print("✅ CLI module import successful")
    except Exception as e:
        print(f"❌ CLI module import failed: {e}")
        return False
    
    # Test 4: Server startup with detailed monitoring
    print("\n4️⃣ Testing server startup with detailed monitoring...")
    
    port = 8600
    
    # Create a monitored subprocess
    cmd = [sys.executable, "-m", "vibecode.cli", "start", "--no-tunnel", "--port", str(port)]
    print(f"   Command: {' '.join(cmd)}")
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
        universal_newlines=True
    )
    
    print("   Server process started, monitoring output...")
    
    # Monitor process with timeout
    startup_events = {
        "process_started": True,
        "mcp_server_import": False,
        "server_creation": False,
        "endpoint_ready": False,
        "port_listening": False,
        "server_ready": False
    }
    
    mcp_path = None
    errors = []
    output_lines = []
    
    def read_stdout():
        """Thread to read stdout."""
        try:
            for line in iter(proc.stdout.readline, ''):
                if line:
                    output_lines.append(("stdout", line.strip()))
        except:
            pass
    
    def read_stderr():
        """Thread to read stderr."""
        try:
            for line in iter(proc.stderr.readline, ''):
                if line:
                    output_lines.append(("stderr", line.strip()))
        except:
            pass
    
    # Start reader threads
    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    
    start_time = time.time()
    timeout = 60  # 60 second timeout
    
    while time.time() - start_time < timeout:
        # Check if process is still running
        if proc.poll() is not None:
            print(f"   ❌ Process terminated with code: {proc.returncode}")
            break
        
        # Process output lines
        while output_lines:
            source, line = output_lines.pop(0)
            print(f"   [{source}] {line}")
            
            # Track startup events
            if "Initializing MCP server endpoint" in line:
                startup_events["mcp_server_import"] = True
            elif "MCP endpoint ready at:" in line:
                startup_events["endpoint_ready"] = True
                # Extract MCP path
                parts = line.split("MCP endpoint ready at:")
                if len(parts) > 1:
                    mcp_path = parts[1].strip()
            elif "Starting server on" in line:
                startup_events["server_creation"] = True
            elif "Server is ready" in line:
                startup_events["server_ready"] = True
            elif "error" in line.lower() or "failed" in line.lower():
                errors.append(line)
        
        # Check if port is listening
        if not startup_events["port_listening"]:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    result = s.connect_ex(('127.0.0.1', port))
                    if result == 0:
                        startup_events["port_listening"] = True
                        print(f"   ✅ Port {port} is now listening")
            except:
                pass
        
        # Check if we have all critical events
        if (startup_events["endpoint_ready"] and 
            startup_events["port_listening"] and 
            startup_events["server_ready"]):
            print("   ✅ All startup events completed")
            break
        
        time.sleep(1)
    
    # Final status check
    elapsed = time.time() - start_time
    
    print(f"\n📊 STARTUP DIAGNOSIS RESULTS (after {elapsed:.1f}s)")
    print("=" * 40)
    
    for event, status in startup_events.items():
        symbol = "✅" if status else "❌"
        print(f"{symbol} {event}: {status}")
    
    if mcp_path:
        print(f"📍 MCP path: {mcp_path}")
    
    if errors:
        print(f"\n❌ ERRORS DETECTED:")
        for error in errors:
            print(f"   {error}")
    
    # Test server functionality if ready
    server_functional = False
    if startup_events["port_listening"] and mcp_path:
        print(f"\n5️⃣ Testing server functionality...")
        try:
            import requests
            
            # Test health endpoint
            health_response = requests.get(f"http://localhost:{port}/health", timeout=5)
            print(f"   Health check: {health_response.status_code}")
            
            # Test MCP endpoint
            mcp_response = requests.post(
                f"http://localhost:{port}{mcp_path}",
                json={
                    "jsonrpc": "2.0",
                    "id": "test",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {}
                    }
                },
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            print(f"   MCP initialize: {mcp_response.status_code}")
            
            if health_response.status_code == 200 and mcp_response.status_code == 200:
                server_functional = True
                print("   ✅ Server is functional")
            
        except Exception as e:
            print(f"   ❌ Functionality test failed: {e}")
    
    # Cleanup
    print(f"\n🧹 Cleaning up...")
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    
    # Final assessment
    success = (
        startup_events["endpoint_ready"] and
        startup_events["port_listening"] and
        server_functional
    )
    
    print(f"\n🎯 FINAL ASSESSMENT: {'✅ SUCCESS' if success else '❌ FAILURE'}")
    
    if not success:
        print("\n💡 TROUBLESHOOTING RECOMMENDATIONS:")
        if not startup_events["mcp_server_import"]:
            print("   - Check MCP server dependencies")
        if not startup_events["endpoint_ready"]:
            print("   - Check server initialization process")
        if not startup_events["port_listening"]:
            print("   - Check port availability and binding")
        if not server_functional:
            print("   - Check server request handling")
    
    return success


def test_minimal_server_implementation():
    """Test a minimal server implementation to isolate issues."""
    print("\n🔍 TESTING MINIMAL SERVER IMPLEMENTATION")
    print("=" * 50)
    
    # Create a minimal test server
    minimal_server_code = '''
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

async def health(request):
    return JSONResponse({"status": "ok", "server": "minimal"})

async def mcp_endpoint(request):
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": "test",
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "minimal", "version": "1.0.0"}
        }
    })

app = Starlette(routes=[
    Route("/health", health, methods=["GET"]),
    Route("/mcp", mcp_endpoint, methods=["POST"]),
])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8601, log_level="info")
'''
    
    # Write minimal server to temp file
    temp_server_path = Path("/tmp/minimal_server.py")
    with open(temp_server_path, "w") as f:
        f.write(minimal_server_code)
    
    print("1️⃣ Starting minimal server...")
    
    proc = subprocess.Popen([
        sys.executable, str(temp_server_path)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Wait for startup
    time.sleep(5)
    
    # Test minimal server
    try:
        import requests
        
        health_response = requests.get("http://localhost:8601/health", timeout=5)
        mcp_response = requests.post(
            "http://localhost:8601/mcp",
            json={"jsonrpc": "2.0", "id": "test", "method": "initialize", "params": {}},
            timeout=5
        )
        
        minimal_works = (
            health_response.status_code == 200 and
            mcp_response.status_code == 200
        )
        
        print(f"✅ Minimal server: {'Working' if minimal_works else 'Failed'}")
        
    except Exception as e:
        print(f"❌ Minimal server test failed: {e}")
        minimal_works = False
    
    # Cleanup
    proc.terminate()
    proc.wait()
    temp_server_path.unlink()
    
    return minimal_works


def main():
    """Main test execution."""
    print("🚀 SERVER STARTUP DIAGNOSIS AND FIX")
    print("=" * 60)
    
    # Test 1: Diagnose current server startup
    server_success = test_server_startup_diagnosis()
    
    # Test 2: Test minimal implementation
    minimal_success = test_minimal_server_implementation()
    
    print(f"\n📊 DIAGNOSIS SUMMARY")
    print("=" * 30)
    print(f"{'✅' if server_success else '❌'} Full server startup: {server_success}")
    print(f"{'✅' if minimal_success else '❌'} Minimal server: {minimal_success}")
    
    if minimal_success and not server_success:
        print(f"\n💡 CONCLUSION: Issue is in VibeCode server implementation")
        print("   Minimal server works, so the problem is specific to VibeCode")
    elif not minimal_success:
        print(f"\n💡 CONCLUSION: Environment issue")
        print("   Basic server functionality is broken")
    else:
        print(f"\n💡 CONCLUSION: All servers working correctly")
        print("   Previous timeout may have been a race condition")


if __name__ == "__main__":
    main()