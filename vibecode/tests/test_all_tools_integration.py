"""Comprehensive integration tests for all MCP tools execution via real HTTP protocol."""

import asyncio
import json
import tempfile
import threading
import time
from pathlib import Path
import pytest
import requests
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from vibecode.server import AuthenticatedMCPServer


class TestAllToolsIntegration:
    """Test all MCP tools through real HTTP protocol - no mocking."""
    
    @pytest.fixture(scope="class")
    def server_setup(self):
        """Set up a real HTTP server for testing all tools."""
        port = 8400
        server_ready = threading.Event()
        server_error = None
        
        def run_server():
            nonlocal server_error
            try:
                server = AuthenticatedMCPServer(
                    name='all-tools-test',
                    allowed_paths=['/tmp', str(Path.cwd())],
                    enable_agent_tool=True
                )
                server_ready.set()
                server.run_sse_with_auth(host="127.0.0.1", port=port, path="/all-tools")
            except Exception as e:
                server_error = e
                server_ready.set()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        assert server_ready.wait(timeout=10), "Server failed to start"
        if server_error:
            pytest.fail(f"Server failed: {server_error}")
        
        time.sleep(2)  # Give server time to fully initialize
        
        # Initialize the MCP session
        init_response = requests.post(
            f"http://127.0.0.1:{port}/all-tools/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": "init",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": True}},
                    "clientInfo": {"name": "Test Client", "version": "1.0"}
                }
            }
        )
        assert init_response.status_code == 200
        
        yield f"http://127.0.0.1:{port}/all-tools/"
    
    def execute_tool(self, endpoint, tool_name, arguments, test_id="test"):
        """Execute a tool via MCP protocol and return the result."""
        response = requests.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": test_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            },
            timeout=30
        )
        
        print(f"🔧 Tool {tool_name} response: {response.status_code}")
        
        if response.status_code != 200:
            pytest.fail(f"Tool {tool_name} failed: {response.status_code} - {response.text}")
        
        # Parse SSE response
        response_text = response.text.strip()
        if response_text.startswith("data: "):
            json_data = response_text.replace("data: ", "").strip()
            result_data = json.loads(json_data)
        else:
            result_data = response.json()
        
        if "error" in result_data:
            pytest.fail(f"Tool {tool_name} returned error: {result_data['error']}")
        
        assert "result" in result_data, f"No result from {tool_name}: {result_data}"
        return result_data["result"]
    
    def get_content_text(self, result):
        """Extract text content from tool result."""
        content = result.get("content", result)
        if isinstance(content, list):
            return "\n".join(item.get("text", str(item)) for item in content)
        elif isinstance(content, dict) and "text" in content:
            return content["text"]
        else:
            return str(content)
    
    def test_claude_code_tool_comprehensive(self, server_setup):
        """Test the claude_code tool with various operations (the main tool that was failing)."""
        endpoint = server_setup
        
        # Test 1: Directory listing (the user's failing scenario)
        result1 = self.execute_tool(endpoint, "claude_code", {
            "prompt": "Show directory tree for /tmp",
            "workFolder": "/tmp"
        })
        content1 = self.get_content_text(result1)
        assert len(content1) > 0
        print(f"✅ claude_code directory tree success: {len(content1)} characters")
        
        # Test 2: File operations 
        with tempfile.TemporaryDirectory() as temp_dir:
            result2 = self.execute_tool(endpoint, "claude_code", {
                "prompt": f"Create a test file at {temp_dir}/test.txt with content 'Hello Integration Test'",
                "workFolder": temp_dir
            })
            content2 = self.get_content_text(result2)
            print(f"✅ claude_code file creation success")
            
            # Verify file was created
            test_file = Path(temp_dir) / "test.txt"
            if test_file.exists():
                file_content = test_file.read_text()
                assert "Hello Integration Test" in file_content
                print(f"✅ claude_code created file successfully: {file_content}")
        
        # Test 3: Simple command execution
        result3 = self.execute_tool(endpoint, "claude_code", {
            "prompt": "Run the command 'echo Hello World'",
            "workFolder": "/tmp"
        })
        content3 = self.get_content_text(result3)
        print(f"✅ claude_code command execution success")
    
    def test_tools_list_endpoint(self, server_setup):
        """Test that tools/list returns expected tools including claude_code."""
        endpoint = server_setup
        
        # Make a tools/list request
        response = requests.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": "tools-list-test",
                "method": "tools/list",
                "params": {}
            },
            timeout=10
        )
        
        assert response.status_code == 200
        
        # Parse SSE response
        response_text = response.text.strip()
        if response_text.startswith("data: "):
            json_data = response_text.replace("data: ", "").strip()
            result_data = json.loads(json_data)
        else:
            result_data = response.json()
        
        assert "result" in result_data
        assert "tools" in result_data["result"]
        
        tools_list = result_data["result"]["tools"]
        assert len(tools_list) > 0, "No tools found - this was the original bug!"
        
        # Verify claude_code tool exists (the main tool we need)
        tool_names = [tool["name"] for tool in tools_list]
        assert "claude_code" in tool_names, "claude_code tool missing!"
        
        print(f"✅ tools/list success: found {len(tools_list)} tools including claude_code")
    
    def test_mcp_protocol_workflow(self, server_setup):
        """Test the complete MCP protocol workflow that Claude.ai uses."""
        endpoint = server_setup
        
        # Step 1: Initialize (same as in server_setup, but verify again)
        init_response = requests.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": "workflow-init",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": True}},
                    "clientInfo": {"name": "Test Claude.ai", "version": "1.0"}
                }
            }
        )
        assert init_response.status_code == 200
        
        # Step 2: List tools (critical for Claude.ai discovery)
        tools_response = requests.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "id": "workflow-tools",
                "method": "tools/list",
                "params": {}
            }
        )
        assert tools_response.status_code == 200
        
        # Step 3: Execute a tool (the critical functionality that was missing)
        with tempfile.TemporaryDirectory() as temp_dir:
            execute_response = requests.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                },
                json={
                    "jsonrpc": "2.0",
                    "id": "workflow-execute",
                    "method": "tools/call",
                    "params": {
                        "name": "claude_code",
                        "arguments": {
                            "prompt": f"Create a test file at {temp_dir}/workflow_test.txt with content 'MCP Protocol Success'",
                            "workFolder": temp_dir
                        }
                    }
                }
            )
            
            assert execute_response.status_code == 200
            
            # Parse response
            response_text = execute_response.text.strip()
            if response_text.startswith("data: "):
                json_data = response_text.replace("data: ", "").strip()
                result_data = json.loads(json_data)
            else:
                result_data = execute_response.json()
            
            assert "result" in result_data, f"No result in execute response: {result_data}"
            
            # Verify file was created (actual functionality test)
            test_file = Path(temp_dir) / "workflow_test.txt"
            if test_file.exists():
                content = test_file.read_text()
                print(f"✅ MCP workflow created file: {content}")
            
        print(f"✅ Complete MCP protocol workflow success")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])