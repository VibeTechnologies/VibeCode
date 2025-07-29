#!/usr/bin/env python3
"""Comprehensive end-to-end integration tests for all MCP tools exposed by VibeCode."""

import subprocess
import sys
import time
import pytest
import requests
import json
import threading
import uuid
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, Any, List, Tuple, Optional


class MCPTestClient:
    """Test client for MCP JSON-RPC protocol."""
    
    def __init__(self, base_url: str, mcp_path: str):
        self.base_url = base_url
        self.mcp_path = mcp_path
        self.mcp_url = f"{base_url}{mcp_path}"
        self.request_id = 1
        
    def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send MCP JSON-RPC request and return response."""
        request_data = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self.request_id,
            "params": params or {}
        }
        self.request_id += 1
        
        response = requests.post(
            self.mcp_url,
            json=request_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            },
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
        
        # Parse SSE response
        content = response.text
        if content.startswith("data: "):
            json_data = content[6:].strip()
            try:
                return json.loads(json_data)
            except json.JSONDecodeError as e:
                print(f"Failed to decode JSON: {json_data}")
                raise e
        else:
            raise Exception(f"Invalid SSE format: {content}")
    
    def initialize(self) -> Dict[str, Any]:
        """Initialize MCP session."""
        return self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        })
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools."""
        response = self.send_request("tools/list")
        return response.get("result", {}).get("tools", [])
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool."""
        return self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })


@contextmanager
def run_vibecode_server(port: int, use_tunnel: bool = False, tunnel_type: str = "quick"):
    """Context manager to run VibeCode server and manage lifecycle."""
    
    # Prepare command
    cmd = [sys.executable, "-m", "vibecode.cli", "start", "--port", str(port)]
    
    if not use_tunnel:
        cmd.append("--no-tunnel")
    elif tunnel_type == "quick":
        cmd.append("--quick")
    
    print(f"Starting VibeCode with command: {' '.join(cmd)}")
    
    # Start process
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    server_info = {
        "base_url": None,
        "mcp_path": None,
        "tunnel_url": None,
        "ready": False,
        "error": None
    }
    
    def monitor_output():
        """Monitor server output for startup indicators."""
        try:
            for line in proc.stderr:
                line_clean = line.strip()
                if not line_clean:
                    continue
                    
                print(f"[VibeCode] {line_clean}")
                
                # Look for server ready indicators
                if "Server is ready on port" in line_clean:
                    if use_tunnel:
                        # Wait for tunnel URL
                        continue
                    else:
                        server_info["base_url"] = f"http://localhost:{port}"
                        print(f"[Test] Set base URL: {server_info['base_url']}")
                        # Check if we already have MCP path - if so, we're ready
                        if server_info.get("mcp_path"):
                            server_info["ready"] = True
                            print(f"[Test] Server ready (late): {server_info['base_url']}{server_info['mcp_path']}")
                
                # Look for tunnel URL
                if "✅ Found tunnel URL:" in line_clean:
                    # Extract tunnel URL
                    parts = line_clean.split("✅ Found tunnel URL:")
                    if len(parts) > 1:
                        tunnel_url = parts[1].strip()
                        server_info["tunnel_url"] = tunnel_url
                        server_info["base_url"] = tunnel_url
                        
                # Look for MCP path
                if "MCP endpoint ready at:" in line_clean:
                    parts = line_clean.split("MCP endpoint ready at:")
                    if len(parts) > 1:
                        mcp_path = parts[1].strip()
                        server_info["mcp_path"] = mcp_path
                        print(f"[Test] Detected MCP path: {mcp_path}")
                        
                        # If we have both URL and path, we're ready
                        if server_info["base_url"]:
                            server_info["ready"] = True
                            print(f"[Test] Server ready: {server_info['base_url']}{mcp_path}")

                # Alternative way to detect MCP endpoint from server logs
                if "Starting server on" in line_clean and "with MCP at" in line_clean:
                    # Extract path from "Starting server on 0.0.0.0:8402 with MCP at /06b964316eec4a2799b7155597a413e6"
                    parts = line_clean.split("with MCP at")
                    if len(parts) > 1:
                        mcp_path = parts[1].strip()
                        server_info["mcp_path"] = mcp_path
                        print(f"[Test] Detected MCP path from server log: {mcp_path}")
                        
                        # If we have both URL and path, we're ready
                        if server_info["base_url"]:
                            server_info["ready"] = True
                            print(f"[Test] Server ready: {server_info['base_url']}{mcp_path}")
                
                # Look for errors
                if "ERROR" in line_clean or "CRITICAL" in line_clean:
                    server_info["error"] = line_clean
                    
        except Exception as e:
            server_info["error"] = f"Output monitoring error: {e}"
    
    # Start output monitoring thread
    monitor_thread = threading.Thread(target=monitor_output, daemon=True)
    monitor_thread.start()
    
    try:
        # Wait for server to be ready
        max_wait = 120 if use_tunnel else 30  # Tunnels take longer
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if server_info["ready"]:
                break
            if server_info["error"]:
                raise Exception(f"Server startup error: {server_info['error']}")
            if proc.poll() is not None:
                raise Exception(f"Server process exited early with code {proc.returncode}")
            time.sleep(1)
        
        if not server_info["ready"]:
            raise Exception(f"Server failed to start within {max_wait} seconds")
        
        print(f"✅ VibeCode server ready at {server_info['base_url']}{server_info['mcp_path']}")
        
        yield server_info
        
    finally:
        # Cleanup
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class TestQuickTunnelInvestigation:
    """Investigate the `vibecode start --quick` tunnel failure issue."""
    
    def test_quick_tunnel_startup_investigation(self):
        """Investigate why quick tunnel fails to work properly."""
        print("\n🔍 Investigating quick tunnel startup issues...")
        
        try:
            with run_vibecode_server(8400, use_tunnel=True, tunnel_type="quick") as server_info:
                # If we get here, the tunnel started successfully
                print(f"✅ Quick tunnel started successfully!")
                print(f"   Base URL: {server_info['base_url']}")
                print(f"   MCP Path: {server_info['mcp_path']}")
                
                # Test basic connectivity
                if server_info["base_url"] and server_info["mcp_path"]:
                    client = MCPTestClient(server_info["base_url"], server_info["mcp_path"])
                    
                    # Test MCP initialize
                    init_response = client.initialize()
                    assert "result" in init_response, f"Initialize failed: {init_response}"
                    print("✅ MCP initialize successful through tunnel")
                    
                    # Test tool listing
                    tools = client.list_tools()
                    print(f"✅ Found {len(tools)} tools through tunnel")
                    
                    return True  # Test passed!
                
        except Exception as e:
            print(f"❌ Quick tunnel investigation revealed issue: {e}")
            
            # Let's try to understand what's happening by running with more detailed logging
            print("\n🔍 Running with detailed logging to understand the issue...")
            
            # Start the process and capture detailed output
            proc = subprocess.Popen([
                sys.executable, "-m", "vibecode.cli", "start", "--quick", "--port", "8401"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            stdout_lines = []
            stderr_lines = []
            
            try:
                # Capture output for detailed analysis
                start_time = time.time()
                while time.time() - start_time < 60:  # 1 minute max
                    if proc.poll() is not None:
                        break
                    
                    # Read available output
                    import select
                    ready, _, _ = select.select([proc.stdout, proc.stderr], [], [], 0.1)
                    
                    for stream in ready:
                        line = stream.readline()
                        if line:
                            line = line.strip()
                            if stream == proc.stdout:
                                stdout_lines.append(line)
                                print(f"[STDOUT] {line}")
                            else:
                                stderr_lines.append(line)
                                print(f"[STDERR] {line}")
                
                # Analyze the collected output
                print("\n📊 Analysis of collected output:")
                print(f"   STDOUT lines: {len(stdout_lines)}")
                print(f"   STDERR lines: {len(stderr_lines)}")
                
                # Look for specific patterns
                cloudflared_started = any("cloudflared" in line.lower() for line in stderr_lines)
                tunnel_url_found = any("tunnel url" in line.lower() for line in stderr_lines)
                server_ready = any("server is ready" in line.lower() for line in stderr_lines)
                
                print(f"   Cloudflared started: {cloudflared_started}")
                print(f"   Tunnel URL found: {tunnel_url_found}")
                print(f"   Server ready: {server_ready}")
                
                # Report findings
                if not cloudflared_started:
                    print("🚨 ISSUE: Cloudflared did not start properly")
                elif not tunnel_url_found:
                    print("🚨 ISSUE: Tunnel URL was not found/parsed correctly")
                elif not server_ready:
                    print("🚨 ISSUE: Server did not become ready")
                else:
                    print("🤔 ISSUE: Unknown - all components seem to start but connection fails")
                
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
            
            # Re-raise the original exception with additional context
            raise Exception(f"Quick tunnel investigation failed: {e}. See analysis above for details.")
    
    def test_local_mode_baseline_working(self):
        """Verify that local mode works as a baseline."""
        print("\n✅ Testing local mode as baseline...")
        
        with run_vibecode_server(8402, use_tunnel=False) as server_info:
            print(f"✅ Local server started successfully!")
            
            # Test MCP connectivity
            client = MCPTestClient(server_info["base_url"], server_info["mcp_path"])
            
            # Test initialize
            init_response = client.initialize()
            assert "result" in init_response, f"Initialize failed: {init_response}"
            print("✅ MCP initialize successful in local mode")
            
            # Test tool listing
            tools = client.list_tools()
            print(f"✅ Found {len(tools)} tools in local mode")
            assert len(tools) > 0, "Should have tools available"


class TestAllMCPTools:
    """Comprehensive tests for all 17 MCP tools exposed by VibeCode."""
    
    def test_all_tools_comprehensive(self):
        """Test all available MCP tools comprehensively."""
        print("\n🧪 Testing all MCP tools comprehensively...")
        
        with run_vibecode_server(8403, use_tunnel=False) as server_info:
            client = MCPTestClient(server_info["base_url"], server_info["mcp_path"])
            
            # Initialize session
            init_response = client.initialize()
            assert "result" in init_response, f"Initialize failed: {init_response}"
            
            # Get all available tools
            tools = client.list_tools()
            print(f"📋 Found {len(tools)} total tools")
            
            tool_names = [tool["name"] for tool in tools]
            print(f"📋 Available tools: {', '.join(tool_names)}")
            
            # Create temporary test directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                test_file = temp_path / "test.txt"
                test_file.write_text("Hello World\nLine 2\nLine 3")
                
                # Test results collector
                test_results = {}
                
                # Test 1: read tool
                if "read" in tool_names:
                    try:
                        result = client.call_tool("read", {"file_path": str(test_file)})
                        test_results["read"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   read: {test_results['read']}")
                    except Exception as e:
                        test_results["read"] = f"❌ EXCEPTION: {e}"
                        print(f"   read: {test_results['read']}")
                
                # Test 2: write tool
                if "write" in tool_names:
                    try:
                        new_file = temp_path / "new_file.txt"
                        result = client.call_tool("write", {
                            "file_path": str(new_file),
                            "content": "New file content"
                        })
                        test_results["write"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   write: {test_results['write']}")
                    except Exception as e:
                        test_results["write"] = f"❌ EXCEPTION: {e}"
                        print(f"   write: {test_results['write']}")
                
                # Test 3: edit tool
                if "edit" in tool_names:
                    try:
                        result = client.call_tool("edit", {
                            "file_path": str(test_file),
                            "old_string": "Hello World",
                            "new_string": "Hello Universe"
                        })
                        test_results["edit"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   edit: {test_results['edit']}")
                    except Exception as e:
                        test_results["edit"] = f"❌ EXCEPTION: {e}"
                        print(f"   edit: {test_results['edit']}")
                
                # Test 4: multi_edit tool
                if "multi_edit" in tool_names:
                    try:
                        edits = [
                            {"old_string": "Line 2", "new_string": "Modified Line 2"},
                            {"old_string": "Line 3", "new_string": "Modified Line 3"}
                        ]
                        result = client.call_tool("multi_edit", {
                            "file_path": str(test_file),
                            "edits": edits
                        })
                        test_results["multi_edit"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   multi_edit: {test_results['multi_edit']}")
                    except Exception as e:
                        test_results["multi_edit"] = f"❌ EXCEPTION: {e}"
                        print(f"   multi_edit: {test_results['multi_edit']}")
                
                # Test 5: directory_tree tool
                if "directory_tree" in tool_names:
                    try:
                        result = client.call_tool("directory_tree", {"path": str(temp_path)})
                        test_results["directory_tree"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   directory_tree: {test_results['directory_tree']}")
                    except Exception as e:
                        test_results["directory_tree"] = f"❌ EXCEPTION: {e}"
                        print(f"   directory_tree: {test_results['directory_tree']}")
                
                # Test 6: grep tool
                if "grep" in tool_names:
                    try:
                        result = client.call_tool("grep", {
                            "pattern": "Hello",
                            "path": str(temp_path)
                        })
                        test_results["grep"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   grep: {test_results['grep']}")
                    except Exception as e:
                        test_results["grep"] = f"❌ EXCEPTION: {e}"
                        print(f"   grep: {test_results['grep']}")
                
                # Test 7: content_replace tool
                if "content_replace" in tool_names:
                    try:
                        result = client.call_tool("content_replace", {
                            "path": str(temp_path),
                            "pattern": "Universe",
                            "replacement": "Galaxy",
                            "file_pattern": "*.txt",
                            "dry_run": True
                        })
                        test_results["content_replace"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   content_replace: {test_results['content_replace']}")
                    except Exception as e:
                        test_results["content_replace"] = f"❌ EXCEPTION: {e}"
                        print(f"   content_replace: {test_results['content_replace']}")
                
                # Test 8: grep_ast tool
                if "grep_ast" in tool_names:
                    try:
                        # Create a Python file for AST testing
                        py_file = temp_path / "test.py"
                        py_file.write_text("def hello():\n    print('Hello World')\n    return True")
                        
                        result = client.call_tool("grep_ast", {
                            "pattern": "def",
                            "path": str(py_file)
                        })
                        test_results["grep_ast"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   grep_ast: {test_results['grep_ast']}")
                    except Exception as e:
                        test_results["grep_ast"] = f"❌ EXCEPTION: {e}"
                        print(f"   grep_ast: {test_results['grep_ast']}")
                
                # Test 9: notebook_read tool (create a dummy notebook)
                if "notebook_read" in tool_names:
                    try:
                        notebook_file = temp_path / "test.ipynb"
                        notebook_content = {
                            "cells": [
                                {
                                    "cell_type": "code",
                                    "source": ["print('Hello from notebook')"],
                                    "outputs": []
                                }
                            ],
                            "metadata": {},
                            "nbformat": 4,
                            "nbformat_minor": 4
                        }
                        notebook_file.write_text(json.dumps(notebook_content))
                        
                        result = client.call_tool("notebook_read", {"notebook_path": str(notebook_file)})
                        test_results["notebook_read"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   notebook_read: {test_results['notebook_read']}")
                    except Exception as e:
                        test_results["notebook_read"] = f"❌ EXCEPTION: {e}"
                        print(f"   notebook_read: {test_results['notebook_read']}")
                
                # Test 10: notebook_edit tool
                if "notebook_edit" in tool_names:
                    try:
                        result = client.call_tool("notebook_edit", {
                            "notebook_path": str(notebook_file),
                            "cell_number": 0,
                            "new_source": "print('Modified notebook cell')"
                        })
                        test_results["notebook_edit"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   notebook_edit: {test_results['notebook_edit']}")
                    except Exception as e:
                        test_results["notebook_edit"] = f"❌ EXCEPTION: {e}"
                        print(f"   notebook_edit: {test_results['notebook_edit']}")
                
                # Test 11: run_command tool
                if "run_command" in tool_names:
                    try:
                        result = client.call_tool("run_command", {
                            "command": "echo 'Hello from command'",
                            "session_id": "test_session"
                        })
                        test_results["run_command"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   run_command: {test_results['run_command']}")
                    except Exception as e:
                        test_results["run_command"] = f"❌ EXCEPTION: {e}"
                        print(f"   run_command: {test_results['run_command']}")
                
                # Test 12: todo_read tool
                if "todo_read" in tool_names:
                    try:
                        result = client.call_tool("todo_read", {"session_id": "test_session"})
                        test_results["todo_read"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   todo_read: {test_results['todo_read']}")
                    except Exception as e:
                        test_results["todo_read"] = f"❌ EXCEPTION: {e}"
                        print(f"   todo_read: {test_results['todo_read']}")
                
                # Test 13: todo_write tool
                if "todo_write" in tool_names:
                    try:
                        todos = [
                            {"id": "1", "content": "Test todo", "status": "pending", "priority": "low"}
                        ]
                        result = client.call_tool("todo_write", {
                            "session_id": "test_session",
                            "todos": todos
                        })
                        test_results["todo_write"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   todo_write: {test_results['todo_write']}")
                    except Exception as e:
                        test_results["todo_write"] = f"❌ EXCEPTION: {e}"
                        print(f"   todo_write: {test_results['todo_write']}")
                
                # Test 14: dispatch_agent tool
                if "dispatch_agent" in tool_names:
                    try:
                        result = client.call_tool("dispatch_agent", {
                            "description": "Test agent task",
                            "prompt": "List files in current directory"
                        })
                        test_results["dispatch_agent"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   dispatch_agent: {test_results['dispatch_agent']}")
                    except Exception as e:
                        test_results["dispatch_agent"] = f"❌ EXCEPTION: {e}"
                        print(f"   dispatch_agent: {test_results['dispatch_agent']}")
                
                # Test 15: batch tool
                if "batch" in tool_names:
                    try:
                        operations = [
                            {"tool": "read", "arguments": {"file_path": str(test_file)}},
                            {"tool": "directory_tree", "arguments": {"path": str(temp_path)}}
                        ]
                        result = client.call_tool("batch", {"operations": operations})
                        test_results["batch"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   batch: {test_results['batch']}")
                    except Exception as e:
                        test_results["batch"] = f"❌ EXCEPTION: {e}"
                        print(f"   batch: {test_results['batch']}")
                
                # Test 16: think tool
                if "think" in tool_names:
                    try:
                        result = client.call_tool("think", {
                            "content": "Testing the think tool functionality"
                        })
                        test_results["think"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   think: {test_results['think']}")
                    except Exception as e:
                        test_results["think"] = f"❌ EXCEPTION: {e}"
                        print(f"   think: {test_results['think']}")
                
                # Test 17: claude_code tool (the flagship tool)
                if "claude_code" in tool_names:
                    try:
                        result = client.call_tool("claude_code", {
                            "prompt": "List the files in this directory",
                            "workFolder": str(temp_path)
                        })
                        test_results["claude_code"] = "✅ SUCCESS" if "result" in result else f"❌ FAIL: {result}"
                        print(f"   claude_code: {test_results['claude_code']}")
                    except Exception as e:
                        test_results["claude_code"] = f"❌ EXCEPTION: {e}"
                        print(f"   claude_code: {test_results['claude_code']}")
                
                # Summary
                total_tools = len(test_results)
                successful_tools = len([r for r in test_results.values() if r.startswith("✅")])
                
                print(f"\n📊 Test Results Summary:")
                print(f"   Total tools tested: {total_tools}")
                print(f"   Successful: {successful_tools}")
                print(f"   Failed: {total_tools - successful_tools}")
                print(f"   Success rate: {successful_tools/total_tools*100:.1f}%")
                
                # Report any failures
                failed_tools = [name for name, result in test_results.items() if not result.startswith("✅")]
                if failed_tools:
                    print(f"❌ Failed tools: {', '.join(failed_tools)}")
                    for tool in failed_tools:
                        print(f"   {tool}: {test_results[tool]}")
                
                # Assert that we tested the expected number of tools
                assert total_tools >= 10, f"Expected to test at least 10 tools, got {total_tools}"
                
                # Assert that most tools work (allow some failures for tools that might not be available)
                success_rate = successful_tools / total_tools
                assert success_rate >= 0.7, f"Success rate too low: {success_rate:.1f} (need >= 70%)"
                
                # Don't return test_results to avoid pytest warning - just assert success
                assert success_rate == 1.0, f"Some tools failed: {failed_tools}"


class TestTunnelConnectivity:
    """Test tunnel connectivity and tool execution through tunnel."""
    
    @pytest.mark.skip(reason="Tunnel tests are slow and may be flaky - run manually when needed")
    def test_tunnel_tool_execution(self):
        """Test that tools work correctly through tunnel connection."""
        print("\n🌐 Testing tool execution through tunnel...")
        
        try:
            with run_vibecode_server(8404, use_tunnel=True, tunnel_type="quick") as server_info:
                client = MCPTestClient(server_info["base_url"], server_info["mcp_path"])
                
                # Initialize session
                init_response = client.initialize()
                assert "result" in init_response, f"Initialize failed: {init_response}"
                print("✅ MCP initialize successful through tunnel")
                
                # Test a few key tools through tunnel
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    test_file = temp_path / "tunnel_test.txt"
                    test_file.write_text("Tunnel test content")
                    
                    # Test read tool through tunnel
                    result = client.call_tool("read", {"file_path": str(test_file)})
                    assert "result" in result, f"Read tool failed through tunnel: {result}"
                    print("✅ Read tool works through tunnel")
                    
                    # Test directory_tree tool through tunnel
                    result = client.call_tool("directory_tree", {"path": str(temp_path)})
                    assert "result" in result, f"Directory tree failed through tunnel: {result}"
                    print("✅ Directory tree tool works through tunnel")
                    
                    # Test run_command tool through tunnel
                    result = client.call_tool("run_command", {
                        "command": "echo 'Hello from tunnel'",
                        "session_id": "tunnel_test"
                    })
                    assert "result" in result, f"Run command failed through tunnel: {result}"
                    print("✅ Run command tool works through tunnel")
                
                print("✅ All tested tools work correctly through tunnel")
                
        except Exception as e:
            pytest.fail(f"Tunnel connectivity test failed: {e}")


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v", "-s"])