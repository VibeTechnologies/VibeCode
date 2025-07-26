#!/usr/bin/env python3
"""Test script for Claude Code integration in VibeCode."""

import asyncio
import sys
from pathlib import Path

# Add the vibecode module to path
sys.path.insert(0, str(Path(__file__).parent / "vibecode"))

from vibecode.server import AuthenticatedMCPServer
from vibecode.claude_code_tool import claude_code_tool


async def test_claude_code_integration():
    """Test the Claude Code integration."""
    print("🧪 Testing VibeCode with Claude Code Integration")
    print("=" * 50)
    
    # Test 1: Server Creation
    print("\n1. Testing server creation...")
    try:
        server = AuthenticatedMCPServer(
            name='vibecode-test',
            allowed_paths=[str(Path.cwd())],
            enable_agent_tool=True
        )
        print("✅ Server created successfully")
        
        # Check tools
        tools = server.mcp_server.mcp._tool_manager._tools
        print(f"✅ Found {len(tools)} tools registered")
        
        if 'claude_code' in tools:
            print("✅ claude_code tool found")
        else:
            print("❌ claude_code tool not found")
            return
            
    except Exception as e:
        print(f"❌ Server creation failed: {e}")
        return
    
    # Test 2: Claude Code Tool Direct Test
    print("\n2. Testing Claude Code tool directly...")
    try:
        result = await claude_code_tool.execute_claude_code(
            "Hello! Please tell me briefly what you are and what you can help with. Do not create or modify any files.",
            work_folder=str(Path.cwd())
        )
        print("✅ Claude Code execution successful")
        print(f"📋 Response: {result[:150]}...")
        
    except Exception as e:
        print(f"❌ Claude Code execution failed: {e}")
        return
    
    # Test 3: File Analysis Test (read-only)
    print("\n3. Testing file analysis capabilities...")
    try:
        result = await claude_code_tool.execute_claude_code(
            "Please analyze the structure of this project. List the main Python files and briefly describe what each does. Do not modify anything.",
            work_folder=str(Path.cwd())
        )
        print("✅ File analysis successful")
        print(f"📋 Analysis preview: {result[:200]}...")
        
    except Exception as e:
        print(f"❌ File analysis failed: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Integration test completed!")
    print("\nTo start the server:")
    print("  vibecode start")
    print("\nThe server will expose 17 tools including the powerful claude_code tool!")


if __name__ == "__main__":
    asyncio.run(test_claude_code_integration())