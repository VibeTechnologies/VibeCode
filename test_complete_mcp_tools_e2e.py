#!/usr/bin/env python3
"""
Complete end-to-end integration test for all 16 MCP tools in VibeCode.
This test uses the working authenticated server configuration.
"""

import subprocess
import sys
import time
import pytest
import requests
import threading
import json
import uuid
import tempfile
import os
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def run_vibecode_authenticated_server(port=8415):
    """Context manager to run vibecode server with authentication (working config)."""
    
    print(f"Starting vibecode authenticated server on port {port}...")
    proc = subprocess.Popen([
        sys.executable, "-m", "vibecode.cli", "start",
        "--port", str(port),
        "--no-tunnel",
        "--reset-uuid"
        # Note: authentication is enabled by default (no --no-auth)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    try:
        # Wait for server to start
        time.sleep(8)  # Longer wait for authenticated server
        
        # Get UUID from config file
        try:
            with open('.vibecode.json', 'r') as f:
                config = json.load(f)
                uuid_hex = config['uuid']
                mcp_url = f"http://localhost:{port}/{uuid_hex}"
                print(f"MCP URL: {mcp_url}")
        except Exception as e:
            raise RuntimeError(f"Could not get UUID from config: {e}")
        
        # Verify server is responding
        health_url = f"http://localhost:{port}/health"
        try:
            health_response = requests.get(health_url, timeout=5)
            if health_response.status_code == 200:
                print(f"✅ Server health check passed: {health_response.json()}")
            else:
                print(f"⚠️  Health check returned {health_response.status_code}")
        except Exception as e:
            print(f"⚠️  Health check failed: {e}")
        
        yield mcp_url, proc
        
    except Exception as e:
        print(f"Error in server context: {e}")
        raise
    finally:
        # Cleanup
        print("Terminating server...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Force killing server...")
            proc.kill()


def make_mcp_request(url: str, method: str, params: dict = None, request_id: int = 1):
    """Make an MCP JSON-RPC request."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id,
        "params": params or {}
    }
    
    response = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    return response


def test_mcp_server_initialization():
    """Test MCP server initialization and basic connectivity."""
    with run_vibecode_authenticated_server() as (mcp_url, proc):
        print(f"\n🧪 Testing MCP server initialization at {mcp_url}")
        
        # Test initialize
        response = make_mcp_request(mcp_url, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        })
        
        print(f"Initialize response status: {response.status_code}")
        
        assert response.status_code == 200, f"Initialize failed: {response.status_code}"
        
        data = response.json()
        print(f"Initialize result: {data}")
        assert data.get("jsonrpc") == "2.0"
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert "capabilities" in data["result"]
        assert "serverInfo" in data["result"]
        
        print("✅ MCP server initialization successful")


def test_all_mcp_tools_list():
    """Test that all expected MCP tools are available."""
    with run_vibecode_authenticated_server() as (mcp_url, proc):
        print(f"\n🧪 Testing MCP tools list at {mcp_url}")
        
        # Get tools list
        response = make_mcp_request(mcp_url, "tools/list")
        
        assert response.status_code == 200, f"Tools list failed: {response.status_code}"
        
        data = response.json()
        assert "result" in data, f"No result in response: {data}"
        
        tools = data["result"]["tools"]
        tool_names = [tool["name"] for tool in tools]
        
        print(f"Available tools ({len(tools)}): {tool_names}")
        
        # Check for expected MCP tools
        expected_tools = [
            # File operations (4 tools)
            "read", "write", "edit", "multi_edit",
            # Search & content (3 tools)
            "grep", "content_replace", "grep_ast", 
            # Directory operations (1 tool)
            "directory_tree",
            # Jupyter notebook (2 tools)
            "notebook_read", "notebook_edit",
            # Execution (1 tool)
            "run_command",
            # Task management (2 tools)
            "todo_read", "todo_write",
            # Advanced tools (3 tools)
            "think", "batch", "claude_code"
        ]
        
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Expected tool '{expected_tool}' not found in {tool_names}"
        
        print(f"✅ All {len(expected_tools)} expected tools are available")
        
        # Verify each tool has proper schema
        for tool in tools:
            assert "name" in tool, f"Tool missing name: {tool}"
            assert "description" in tool, f"Tool missing description: {tool}"
            assert "inputSchema" in tool, f"Tool missing inputSchema: {tool}"
            print(f"  ✓ {tool['name']}: {tool['description'][:50]}...")


def test_file_operations_tools():
    """Test file operation MCP tools: read, write, edit, multi_edit."""
    with run_vibecode_authenticated_server() as (mcp_url, proc):
        print(f"\n🧪 Testing file operations tools at {mcp_url}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test_file.txt")
            
            # Test write tool
            print("  Testing write tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "write",
                "arguments": {
                    "file_path": test_file,
                    "content": "Hello, World!\nThis is a test file.\nLine 3 content."
                }
            }, request_id=1)
            
            assert response.status_code == 200, f"Write tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Write tool no result: {data}"
            print("  ✅ Write tool works")
            
            # Verify file was created
            assert os.path.exists(test_file), "File was not created"
            
            # Test read tool
            print("  Testing read tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "read",
                "arguments": {
                    "file_path": test_file
                }
            }, request_id=2)
            
            assert response.status_code == 200, f"Read tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Read tool no result: {data}"
            # Check content is in the response
            content = data["result"]["content"]
            assert isinstance(content, list), f"Content should be list: {content}"
            print("  ✅ Read tool works")
            
            # Test edit tool
            print("  Testing edit tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "edit",
                "arguments": {
                    "file_path": test_file,
                    "old_string": "Hello, World!",
                    "new_string": "Hello, VibeCode!"
                }
            }, request_id=3)
            
            assert response.status_code == 200, f"Edit tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Edit tool no result: {data}"
            print("  ✅ Edit tool works")
            
            # Test multi_edit tool
            print("  Testing multi_edit tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "multi_edit",
                "arguments": {
                    "file_path": test_file,
                    "edits": [
                        {
                            "old_string": "Line 3",
                            "new_string": "Line Three"
                        }
                    ]
                }
            }, request_id=4)
            
            assert response.status_code == 200, f"Multi-edit tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Multi-edit tool no result: {data}"
            print("  ✅ Multi-edit tool works")


def test_search_and_content_tools():
    """Test search MCP tools: grep, content_replace, grep_ast."""
    with run_vibecode_authenticated_server() as (mcp_url, proc):
        print(f"\n🧪 Testing search and content tools at {mcp_url}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            test_file1 = os.path.join(temp_dir, "test1.py")
            test_file2 = os.path.join(temp_dir, "test2.py")
            
            # Create test files with content
            with open(test_file1, 'w') as f:
                f.write("def hello_world():\n    print('Hello, World!')\n    return 'success'\n")
            
            with open(test_file2, 'w') as f:
                f.write("def goodbye_world():\n    print('Goodbye, World!')\n    return 'finished'\n")
            
            # Test grep tool
            print("  Testing grep tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "grep",
                "arguments": {
                    "pattern": "hello",
                    "path": temp_dir
                }
            }, request_id=5)
            
            assert response.status_code == 200, f"Grep tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Grep tool no result: {data}"
            print("  ✅ Grep tool works")
            
            # Test content_replace tool
            print("  Testing content_replace tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "content_replace",
                "arguments": {
                    "pattern": "World",
                    "replacement": "VibeCode",
                    "path": temp_dir
                }
            }, request_id=6)
            
            assert response.status_code == 200, f"Content replace tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Content replace tool no result: {data}"
            print("  ✅ Content replace tool works")
            
            # Test grep_ast tool
            print("  Testing grep_ast tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "grep_ast",
                "arguments": {
                    "pattern": "def",
                    "path": temp_dir
                }
            }, request_id=7)
            
            assert response.status_code == 200, f"Grep AST tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Grep AST tool no result: {data}"
            print("  ✅ Grep AST tool works")


def test_directory_and_execution_tools():
    """Test directory_tree and run_command tools."""
    with run_vibecode_authenticated_server() as (mcp_url, proc):
        print(f"\n🧪 Testing directory and execution tools at {mcp_url}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create directory structure
            os.makedirs(os.path.join(temp_dir, "subdir"))
            with open(os.path.join(temp_dir, "file1.txt"), 'w') as f:
                f.write("test content")
            with open(os.path.join(temp_dir, "subdir", "file2.txt"), 'w') as f:
                f.write("nested content")
            
            # Test directory_tree tool
            print("  Testing directory_tree tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "directory_tree",
                "arguments": {
                    "path": temp_dir,
                    "depth": 2
                }
            }, request_id=8)
            
            assert response.status_code == 200, f"Directory tree tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Directory tree tool no result: {data}"
            print("  ✅ Directory tree tool works")
            
            # Test run_command tool
            print("  Testing run_command tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "run_command",
                "arguments": {
                    "command": "echo Hello from MCP tool test"
                }
            }, request_id=9)
            
            assert response.status_code == 200, f"Run command tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Run command tool no result: {data}"
            print("  ✅ Run command tool works")


def test_task_management_tools():
    """Test todo_read and todo_write tools.""" 
    with run_vibecode_authenticated_server() as (mcp_url, proc):
        print(f"\n🧪 Testing task management tools at {mcp_url}")
        
        # Test todo_write tool
        print("  Testing todo_write tool...")
        response = make_mcp_request(mcp_url, "tools/call", {
            "name": "todo_write",
            "arguments": {
                "todos": [
                    {
                        "id": "1",
                        "content": "Test todo item",
                        "status": "pending",
                        "priority": "high"
                    },
                    {
                        "id": "2", 
                        "content": "Another test item",
                        "status": "completed",
                        "priority": "medium"
                    }
                ]
            }
        }, request_id=10)
        
        assert response.status_code == 200, f"Todo write tool failed: {response.status_code}"
        data = response.json()
        assert "result" in data, f"Todo write tool no result: {data}"
        print("  ✅ Todo write tool works")
        
        # Test todo_read tool
        print("  Testing todo_read tool...")
        response = make_mcp_request(mcp_url, "tools/call", {
            "name": "todo_read",
            "arguments": {}
        }, request_id=11)
        
        assert response.status_code == 200, f"Todo read tool failed: {response.status_code}"
        data = response.json()
        assert "result" in data, f"Todo read tool no result: {data}"
        print("  ✅ Todo read tool works")


def test_advanced_tools():
    """Test think, batch, and claude_code tools."""
    with run_vibecode_authenticated_server() as (mcp_url, proc):
        print(f"\n🧪 Testing advanced tools at {mcp_url}")
        
        # Test think tool
        print("  Testing think tool...")
        response = make_mcp_request(mcp_url, "tools/call", {
            "name": "think",
            "arguments": {
                "query": "What is the purpose of MCP tools in VibeCode?"
            }
        }, request_id=12)
        
        assert response.status_code == 200, f"Think tool failed: {response.status_code}"
        data = response.json()
        assert "result" in data, f"Think tool no result: {data}"
        print("  ✅ Think tool works")
        
        # Test batch tool
        print("  Testing batch tool...")
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "batch_test.txt")
            
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "batch",
                "arguments": {
                    "operations": [
                        {
                            "name": "write",
                            "arguments": {
                                "file_path": test_file,
                                "content": "Batch test file content"
                            }
                        },
                        {
                            "name": "read",
                            "arguments": {
                                "file_path": test_file
                            }
                        }
                    ]
                }
            }, request_id=13)
            
            assert response.status_code == 200, f"Batch tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Batch tool no result: {data}"
            print("  ✅ Batch tool works")
        
        # Test claude_code tool
        print("  Testing claude_code tool...")
        with tempfile.TemporaryDirectory() as temp_dir:
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "claude_code",
                "arguments": {
                    "prompt": "List the files in the current directory", 
                    "workFolder": temp_dir
                }
            }, request_id=14)
            
            assert response.status_code == 200, f"Claude code tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Claude code tool no result: {data}"
            print("  ✅ Claude code tool works")


def test_notebook_tools():
    """Test notebook_read and notebook_edit tools."""
    with run_vibecode_authenticated_server() as (mcp_url, proc):
        print(f"\n🧪 Testing notebook tools at {mcp_url}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a simple notebook file
            notebook_file = os.path.join(temp_dir, "test.ipynb")
            notebook_content = {
                "cells": [
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": ["print('Hello, Notebook!')"]
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 4
            }
            
            with open(notebook_file, 'w') as f:
                json.dump(notebook_content, f)
            
            # Test notebook_read tool
            print("  Testing notebook_read tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "notebook_read",
                "arguments": {
                    "notebook_path": notebook_file
                }
            }, request_id=15)
            
            assert response.status_code == 200, f"Notebook read tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Notebook read tool no result: {data}"
            print("  ✅ Notebook read tool works")
            
            # Test notebook_edit tool (create new cell)
            print("  Testing notebook_edit tool...")
            response = make_mcp_request(mcp_url, "tools/call", {
                "name": "notebook_edit",
                "arguments": {
                    "notebook_path": notebook_file,
                    "cell_id": "0",
                    "new_source": "print('Modified notebook cell!')"
                }
            }, request_id=16)
            
            assert response.status_code == 200, f"Notebook edit tool failed: {response.status_code}"
            data = response.json()
            assert "result" in data, f"Notebook edit tool no result: {data}" 
            print("  ✅ Notebook edit tool works")


if __name__ == "__main__":
    # Clean up any existing config
    import os
    if os.path.exists('.vibecode.json'):
        os.remove('.vibecode.json')
    
    # Run all tests
    test_functions = [
        test_mcp_server_initialization,
        test_all_mcp_tools_list,
        test_file_operations_tools,
        test_search_and_content_tools,
        test_directory_and_execution_tools,
        test_task_management_tools,
        test_advanced_tools,
        test_notebook_tools,
    ]
    
    print("🚀 Running complete MCP tools E2E tests...")
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            print(f"\n{'='*80}")
            print(f"Running {test_func.__name__}")
            print(f"{'='*80}")
            test_func()
            print(f"✅ {test_func.__name__} PASSED")
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"🎉 Complete MCP tools E2E tests finished!")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Success rate: {passed}/{passed + failed} ({100 * passed // (passed + failed) if passed + failed > 0 else 0}%)")
    print(f"{'='*80}")
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! MCP server is fully functional.")
    else:
        print(f"⚠️  {failed} tests failed. See details above.")