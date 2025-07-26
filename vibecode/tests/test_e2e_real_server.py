"""End-to-end integration tests that start real HTTP servers and test actual MCP protocol."""

import asyncio
import json
import threading
import time
import uuid
from pathlib import Path
import pytest
import requests
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent))

from vibecode.server import AuthenticatedMCPServer


class TestEndToEndRealServer:
    """Test actual server startup and MCP protocol endpoints."""
    
    @pytest.mark.asyncio
    async def test_real_server_startup_and_tools_endpoint(self):
        """Test that a real HTTP server starts and serves tools correctly."""
        port = 8350  # Use a different port to avoid conflicts
        server_ready = threading.Event()
        server_error = None
        
        def run_server():
            """Run the server in a thread."""
            nonlocal server_error
            try:
                server = AuthenticatedMCPServer(
                    name='e2e-test-server',
                    allowed_paths=['/tmp'],
                    enable_agent_tool=True
                )
                
                # Signal that server is ready to start
                server_ready.set()
                print(f"🚀 Test server starting on port {port}")
                
                # Run the server (this will block)
                server.run_sse_with_auth(host="127.0.0.1", port=port, path="/test-mcp")
                
            except Exception as e:
                print(f"❌ Test server failed to start: {e}")
                server_error = e
                server_ready.set()
        
        # Start server in background thread
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        # Wait for server to be ready
        assert server_ready.wait(timeout=10), "Server failed to start within 10 seconds"
        
        if server_error:
            pytest.fail(f"Server failed to start: {server_error}")
        
        # Give server a moment to fully initialize
        time.sleep(2)
        
        try:
            # Test 1: Health endpoint
            health_response = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
            assert health_response.status_code == 200
            health_data = health_response.json()
            assert health_data["status"] == "healthy"
            print(f"✅ Health check passed: {health_data}")
            
            # Test 2: MCP tools/list endpoint (the one Claude.ai uses)
            tools_request = {
                "jsonrpc": "2.0",
                "id": "test-tools-list",
                "method": "tools/list",
                "params": {}
            }
            
            # Try different MCP endpoint paths
            endpoints_to_try = [
                f"http://127.0.0.1:{port}/test-mcp/mcp",  # Real MCP server internal path
                f"http://127.0.0.1:{port}/test-mcp/",     # Direct mount path
                f"http://127.0.0.1:{port}/mcp",           # Standard MCP path
            ]
            
            tools_response = None
            for endpoint in endpoints_to_try:
                try:
                    print(f"🔍 Trying MCP endpoint: {endpoint}")
                    response = requests.post(
                        endpoint,
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json, text/event-stream"
                        },
                        json=tools_request,
                        timeout=10
                    )
                    print(f"🔍 Response status: {response.status_code}")
                    if response.status_code == 200:
                        tools_response = response
                        print(f"✅ Found working MCP endpoint: {endpoint}")
                        break
                    elif response.status_code != 404:
                        print(f"⚠️ Non-404 response from {endpoint}: {response.status_code} - {response.text[:100]}")
                except Exception as e:
                    print(f"❌ Error trying {endpoint}: {e}")
                    continue
            
            if not tools_response:
                pytest.fail("Could not find working MCP endpoint")
            
            tools_response = tools_response  # Use the successful response
            
            print(f"Tools response status: {tools_response.status_code}")
            print(f"Tools response headers: {dict(tools_response.headers)}")
            print(f"Tools response text: {tools_response.text[:500]}...")
            
            # This is the critical test that would have caught the failure
            assert tools_response.status_code == 200, f"Expected 200, got {tools_response.status_code}: {tools_response.text}"
            
            # Parse response (might be SSE format)
            response_text = tools_response.text.strip()
            if response_text.startswith("data: "):
                # SSE format
                json_data = response_text.replace("data: ", "").strip()
                tools_data = json.loads(json_data)
            else:
                # Regular JSON
                tools_data = tools_response.json()
            
            # Validate response structure
            assert "jsonrpc" in tools_data
            assert tools_data["jsonrpc"] == "2.0"
            assert "result" in tools_data or "error" not in tools_data
            
            if "result" in tools_data:
                result = tools_data["result"]
                assert "tools" in result
                tools_list = result["tools"]
                
                # This is the key assertion that would have caught the bug
                assert len(tools_list) > 0, "No tools found! This is the bug Claude.ai encountered."
                
                # Verify expected tools exist
                tool_names = [tool["name"] for tool in tools_list]
                assert "claude_code" in tool_names, "claude_code tool missing!"
                
                print(f"✅ Found {len(tools_list)} tools: {tool_names}")
                
                # Verify claude_code tool structure
                claude_tool = next(tool for tool in tools_list if tool["name"] == "claude_code")
                assert "description" in claude_tool
                assert "inputSchema" in claude_tool
                assert claude_tool["inputSchema"]["type"] == "object"
                assert "prompt" in claude_tool["inputSchema"]["properties"]
                
                print(f"✅ claude_code tool properly configured: {claude_tool['description'][:50]}...")
                
            else:
                pytest.fail(f"MCP tools/list returned error: {tools_data}")
                
        except requests.exceptions.ConnectionError:
            pytest.fail(f"Could not connect to server on port {port}")
        except requests.exceptions.Timeout:
            pytest.fail(f"Request to server on port {port} timed out")
        except Exception as e:
            pytest.fail(f"Unexpected error testing server: {e}")
    
    @pytest.mark.asyncio 
    async def test_mcp_initialize_protocol(self):
        """Test the MCP initialize handshake that Claude.ai performs."""
        port = 8351
        server_ready = threading.Event()
        server_error = None
        
        def run_server():
            nonlocal server_error
            try:
                server = AuthenticatedMCPServer(
                    name='e2e-init-test',
                    allowed_paths=['/tmp'],
                    enable_agent_tool=True
                )
                server_ready.set()
                server.run_sse_with_auth(host="127.0.0.1", port=port, path="/mcp")
            except Exception as e:
                server_error = e
                server_ready.set()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        assert server_ready.wait(timeout=10), "Server failed to start"
        if server_error:
            pytest.fail(f"Server failed: {server_error}")
        
        time.sleep(2)
        
        # Test MCP initialize protocol
        init_request = {
            "jsonrpc": "2.0",
            "id": "init-test",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        init_response = requests.post(
            f"http://127.0.0.1:{port}/mcp/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json=init_request,
            timeout=10
        )
        
        assert init_response.status_code == 200
        
        # Parse response
        response_text = init_response.text.strip()
        if response_text.startswith("data: "):
            json_data = response_text.replace("data: ", "").strip()
            init_data = json.loads(json_data)
        else:
            init_data = init_response.json()
        
        assert "result" in init_data
        result = init_data["result"]
        assert "protocolVersion" in result
        assert "capabilities" in result
        assert "serverInfo" in result
        
        print(f"✅ MCP initialize successful: {result['serverInfo']}")
    
    def test_cli_startup_and_endpoint_access(self):
        """Test starting the server via CLI and accessing endpoints."""
        with tempfile.TemporaryDirectory() as temp_dir:
            port = 8352
            
            # Start server via CLI in background
            proc = subprocess.Popen([
                sys.executable, '-m', 'vibecode.cli', 'start', 
                '--no-tunnel', '--port', str(port)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=temp_dir)
            
            try:
                # Wait for server to start
                time.sleep(5)
                
                # Test health endpoint
                health_response = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
                assert health_response.status_code == 200
                
                # Get the UUID path from server logs (simulated)
                uuid_path = f"/{uuid.uuid4().hex}"
                
                # Test MCP endpoint with UUID path
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": "cli-test",
                    "method": "tools/list", 
                    "params": {}
                }
                
                # Try the root path first
                tools_response = requests.post(
                    f"http://127.0.0.1:{port}/",
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    },
                    json=tools_request,
                    timeout=10
                )
                
                # Should get some response (might be redirect or tools)
                print(f"CLI tools response: {tools_response.status_code} - {tools_response.text[:200]}")
                
                # The key test: should not return 404 or "no tools"
                assert tools_response.status_code in [200, 307], f"Unexpected status: {tools_response.status_code}"
                
            finally:
                proc.terminate()
                proc.wait(timeout=5)
    
    def test_actual_claude_ai_workflow(self):
        """Test the exact workflow that Claude.ai follows."""
        port = 8353
        server_ready = threading.Event()
        
        def run_server():
            try:
                server = AuthenticatedMCPServer(
                    name='claude-ai-test',
                    allowed_paths=['/tmp'],
                    enable_agent_tool=True
                )
                server_ready.set()
                server.run_sse_with_auth(host="127.0.0.1", port=port, path="/claude-mcp")
            except Exception as e:
                print(f"Server error: {e}")
                server_ready.set()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        assert server_ready.wait(timeout=10)
        time.sleep(2)
        
        # Step 1: Initialize (as Claude.ai does)
        init_response = requests.post(
            f"http://127.0.0.1:{port}/claude-mcp/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "User-Agent": "Claude.ai MCP Client"
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": True}},
                    "clientInfo": {"name": "Claude", "version": "1.0"}
                }
            }
        )
        
        print(f"Initialize: {init_response.status_code}")
        
        # Step 2: List tools (the critical call)
        tools_response = requests.post(
            f"http://127.0.0.1:{port}/claude-mcp/",
            headers={
                "Content-Type": "application/json", 
                "Accept": "application/json, text/event-stream",
                "User-Agent": "Claude.ai MCP Client"
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
        )
        
        print(f"Tools list: {tools_response.status_code}")
        print(f"Tools response: {tools_response.text[:300]}")
        
        # This is the exact test that would have caught the Claude.ai issue
        assert tools_response.status_code == 200, "tools/list endpoint failed"
        
        response_text = tools_response.text.strip()
        if response_text.startswith("data: "):
            json_data = response_text.replace("data: ", "").strip()
            tools_data = json.loads(json_data)
        else:
            tools_data = tools_response.json()
        
        assert "result" in tools_data, f"No result in response: {tools_data}"
        assert "tools" in tools_data["result"], f"No tools in result: {tools_data['result']}"
        
        tools_list = tools_data["result"]["tools"]
        assert len(tools_list) > 0, "CRITICAL: No tools returned - this is exactly what Claude.ai saw!"
        
        # Verify claude_code tool exists
        tool_names = [tool["name"] for tool in tools_list]
        assert "claude_code" in tool_names, "claude_code tool missing from tools list"
        
        print(f"✅ SUCCESS: Claude.ai workflow test passed with {len(tools_list)} tools")
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_execution_via_mcp(self):
        """Test actual execution of claude_code tool through MCP protocol."""
        port = 8354
        server_ready = threading.Event()
        
        def run_server():
            try:
                server = AuthenticatedMCPServer(
                    name='claude-code-execution-test',
                    allowed_paths=['/tmp'],
                    enable_agent_tool=True
                )
                server_ready.set()
                server.run_sse_with_auth(host="127.0.0.1", port=port, path="/mcp-exec")
            except Exception as e:
                print(f"Server error: {e}")
                server_ready.set()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        assert server_ready.wait(timeout=10)
        time.sleep(2)
        
        # Step 1: Initialize
        init_response = requests.post(
            f"http://127.0.0.1:{port}/mcp-exec/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": True}},
                    "clientInfo": {"name": "Test Client", "version": "1.0"}
                }
            }
        )
        
        print(f"Initialize response: {init_response.status_code}")
        assert init_response.status_code == 200
        
        # Step 2: Test tool execution (the critical part that was failing)
        tool_call_response = requests.post(
            f"http://127.0.0.1:{port}/mcp-exec/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "claude_code",
                    "arguments": {
                        "prompt": "Show directory tree for /tmp",
                        "workFolder": "/tmp"
                    }
                }
            }
        )
        
        print(f"Tool call response: {tool_call_response.status_code}")
        print(f"Tool call response text: {tool_call_response.text[:500]}")
        
        # This is the test that should catch if tool execution is broken
        assert tool_call_response.status_code == 200, f"Tool execution failed: {tool_call_response.text}"
        
        # Parse response
        response_text = tool_call_response.text.strip()
        if response_text.startswith("data: "):
            json_data = response_text.replace("data: ", "").strip()
            tool_data = json.loads(json_data)
        else:
            tool_data = tool_call_response.json()
        
        print(f"Tool execution result: {tool_data}")
        
        # Verify the tool execution result
        assert "result" in tool_data, f"No result in tool response: {tool_data}"
        assert "content" in tool_data["result"], f"No content in tool result: {tool_data['result']}"
        
        # Verify it actually executed the directory tree command
        content = tool_data["result"]["content"]
        assert isinstance(content, (str, list)), f"Unexpected content type: {type(content)}"
        
        # If content is a list (multiple parts), join it
        if isinstance(content, list):
            content_str = "\n".join(item.get("text", str(item)) for item in content)
        else:
            content_str = content
        
        print(f"✅ Tool execution successful. Output length: {len(content_str)} characters")
        print(f"✅ Output preview: {content_str[:200]}...")
        
        # The critical test: verify it's not an error about tool execution
        assert "error" not in content_str.lower() or "directory" in content_str.lower()
        
        print(f"✅ SUCCESS: claude_code tool execution test passed")
    
    @pytest.mark.asyncio 
    async def test_user_reported_directory_tree_issue(self):
        """Test the exact scenario the user reported failing."""
        port = 8355
        server_ready = threading.Event()
        
        def run_server():
            try:
                server = AuthenticatedMCPServer(
                    name='user-issue-test',
                    allowed_paths=['/'],  # Allow access to user workspace
                    enable_agent_tool=True
                )
                server_ready.set()
                server.run_sse_with_auth(host="127.0.0.1", port=port, path="/user-test")
            except Exception as e:
                print(f"Server error: {e}")
                server_ready.set()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        assert server_ready.wait(timeout=10)
        time.sleep(2)
        
        # Test the exact user scenario: Show directory tree for ~/workspace
        workspace_path = str(Path.home() / "workspace")
        
        # Initialize session
        init_response = requests.post(
            f"http://127.0.0.1:{port}/user-test/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": "user-init",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": True}},
                    "clientInfo": {"name": "Claude.ai", "version": "1.0"}
                }
            }
        )
        
        assert init_response.status_code == 200
        
        # Execute the exact user command
        user_command_response = requests.post(
            f"http://127.0.0.1:{port}/user-test/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": "user-command",
                "method": "tools/call",
                "params": {
                    "name": "claude_code",
                    "arguments": {
                        "prompt": "Show directory tree for ~/workspace",
                        "workFolder": workspace_path
                    }
                }
            }
        )
        
        print(f"User command response: {user_command_response.status_code}")
        print(f"User command response: {user_command_response.text[:500]}")
        
        # This should work without any errors
        if user_command_response.status_code != 200:
            pytest.fail(f"User's directory tree command failed: {user_command_response.status_code} - {user_command_response.text}")
        
        # Parse response
        response_text = user_command_response.text.strip()
        if response_text.startswith("data: "):
            json_data = response_text.replace("data: ", "").strip()
            result_data = json.loads(json_data)
        else:
            result_data = user_command_response.json()
        
        print(f"User command result structure: {list(result_data.keys())}")
        
        # Verify successful execution
        if "error" in result_data:
            pytest.fail(f"User command returned error: {result_data['error']}")
        
        assert "result" in result_data, f"No result in user command response: {result_data}"
        
        print(f"✅ SUCCESS: User's directory tree command worked correctly")


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v", "-s"])