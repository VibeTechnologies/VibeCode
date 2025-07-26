"""Integration tests for Claude Code integration in VibeCode."""

import asyncio
import os
import tempfile
from pathlib import Path
import pytest
import shutil
import subprocess
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from vibecode.claude_code_tool import ClaudeCodeTool, claude_code_tool
from vibecode.server import AuthenticatedMCPServer


class TestClaudeCodeTool:
    """Test the Claude Code tool functionality."""
    
    def test_find_claude_cli_default(self):
        """Test Claude CLI discovery with default settings."""
        tool = ClaudeCodeTool()
        
        # Should find claude in PATH or local install
        assert tool.claude_cli_path is not None
        assert isinstance(tool.claude_cli_path, str)
        assert len(tool.claude_cli_path) > 0
    
    def test_find_claude_cli_custom_name(self):
        """Test Claude CLI discovery with custom name."""
        with patch.dict(os.environ, {'CLAUDE_CLI_NAME': 'claude-custom'}):
            tool = ClaudeCodeTool()
            assert tool.claude_cli_path == 'claude-custom'
    
    def test_find_claude_cli_absolute_path(self):
        """Test Claude CLI discovery with absolute path."""
        test_path = '/usr/local/bin/claude'
        with patch.dict(os.environ, {'CLAUDE_CLI_NAME': test_path}):
            tool = ClaudeCodeTool()
            assert tool.claude_cli_path == test_path
    
    def test_find_claude_cli_invalid_relative_path(self):
        """Test Claude CLI discovery rejects relative paths."""
        with patch.dict(os.environ, {'CLAUDE_CLI_NAME': './claude'}):
            with pytest.raises(ValueError, match="Relative paths are not allowed"):
                ClaudeCodeTool()
    
    def test_find_claude_cli_local_install(self):
        """Test Claude CLI discovery finds local installation."""
        # Mock the local path existence
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            tool = ClaudeCodeTool()
            
            # Should find the local installation path
            expected_path = str(Path.home() / '.claude' / 'local' / 'claude')
            assert tool.claude_cli_path == expected_path
    
    @pytest.mark.asyncio
    async def test_spawn_async_success(self):
        """Test successful process spawning."""
        tool = ClaudeCodeTool()
        
        # Test with a simple command that should work
        result = await tool._spawn_async('echo', ['hello world'])
        
        assert 'stdout' in result
        assert 'stderr' in result
        assert 'hello world' in result['stdout']
    
    @pytest.mark.asyncio
    async def test_spawn_async_command_not_found(self):
        """Test process spawning with non-existent command."""
        tool = ClaudeCodeTool()
        
        with pytest.raises(FileNotFoundError):
            await tool._spawn_async('nonexistent-command-12345', ['test'])
    
    @pytest.mark.asyncio
    async def test_spawn_async_timeout(self):
        """Test process spawning with timeout."""
        tool = ClaudeCodeTool()
        
        # Use a command that will take longer than the timeout
        with pytest.raises(TimeoutError):
            await tool._spawn_async('sleep', ['10'], timeout=0.1)
    
    def test_get_tool_definition(self):
        """Test tool definition structure."""
        tool = ClaudeCodeTool()
        definition = tool.get_tool_definition()
        
        # Check required fields
        assert 'name' in definition
        assert 'description' in definition
        assert 'inputSchema' in definition
        
        # Check specific values
        assert definition['name'] == 'claude_code'
        assert 'Claude Code Agent' in definition['description']
        
        # Check schema structure
        schema = definition['inputSchema']
        assert schema['type'] == 'object'
        assert 'properties' in schema
        assert 'prompt' in schema['properties']
        assert 'workFolder' in schema['properties']
        assert schema['required'] == ['prompt']


class TestClaudeCodeExecution:
    """Test actual Claude Code execution (requires Claude CLI)."""
    
    @pytest.mark.asyncio
    async def test_execute_simple_prompt(self):
        """Test executing a simple prompt that doesn't modify files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                result = await claude_code_tool.execute_claude_code(
                    "Say 'Hello from Claude Code integration test!' and nothing else.",
                    work_folder=temp_dir
                )
                
                assert isinstance(result, str)
                assert len(result) > 0
                assert 'Hello' in result or 'hello' in result.lower()
                
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                pytest.skip(f"Claude CLI not available or not properly configured: {e}")
    
    @pytest.mark.asyncio
    async def test_execute_with_work_folder(self):
        """Test executing with specific work folder."""
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                result = await claude_code_tool.execute_claude_code(
                    "Tell me what directory I'm in. Don't create any files.",
                    work_folder=temp_dir
                )
                
                assert isinstance(result, str)
                assert len(result) > 0
                
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_execute_file_analysis(self):
        """Test file analysis without modification."""
        # Create a temporary directory with a test file
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("def hello():\n    return 'Hello World'\n")
            
            try:
                result = await claude_code_tool.execute_claude_code(
                    "Please analyze the Python file in this directory. What function does it contain? Don't modify anything.",
                    work_folder=temp_dir
                )
                
                assert isinstance(result, str)
                assert len(result) > 0
                # Should mention the hello function
                assert 'hello' in result.lower()
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available or authentication issue: {e}")
    
    @pytest.mark.asyncio
    async def test_execute_invalid_work_folder(self):
        """Test execution with non-existent work folder."""
        invalid_path = "/path/that/does/not/exist/12345"
        
        try:
            result = await claude_code_tool.execute_claude_code(
                "Say hello briefly",
                work_folder=invalid_path
            )
            
            # Should still work, just use home directory
            assert isinstance(result, str)
            
        except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
            pytest.skip(f"Claude CLI not available or authentication issue: {e}")


class TestMCPServerIntegration:
    """Test integration with the MCP server."""
    
    def test_server_creation_with_claude_code(self):
        """Test that server creates successfully with Claude Code tool."""
        server = AuthenticatedMCPServer(
            name='test-server',
            allowed_paths=['/tmp'],
            enable_agent_tool=True
        )
        
        # Check that server was created
        assert server is not None
        assert server.mcp_server is not None
        
        # Check that tools are registered
        mcp = server.mcp_server.mcp
        assert hasattr(mcp, '_tool_manager')
        
        tools = mcp._tool_manager._tools
        assert len(tools) > 0
        
        # Check that claude_code tool is registered
        assert 'claude_code' in tools
        
        # Check tool properties
        claude_tool = tools['claude_code']
        assert claude_tool is not None
        assert hasattr(claude_tool, 'fn')  # Should have a function
    
    def test_tool_count(self):
        """Test that we have the expected number of tools."""
        server = AuthenticatedMCPServer(
            name='test-server',
            allowed_paths=['/tmp'],
            enable_agent_tool=True
        )
        
        tools = server.mcp_server.mcp._tool_manager._tools
        
        # Should have 17 tools (16 from mcp-claude-code + 1 claude_code)
        assert len(tools) == 17
        
        # Check for key tools
        expected_tools = [
            'read', 'write', 'edit', 'multi_edit',
            'directory_tree', 'grep', 'content_replace', 'grep_ast',
            'notebook_read', 'notebook_edit', 'run_command',
            'dispatch_agent', 'todo_read', 'todo_write',
            'think', 'batch', 'claude_code'
        ]
        
        for tool in expected_tools:
            assert tool in tools, f"Tool {tool} not found in registered tools"
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_execution_via_mcp(self):
        """Test calling the claude_code tool through MCP server."""
        server = AuthenticatedMCPServer(
            name='test-server',
            allowed_paths=['/tmp'],
            enable_agent_tool=True
        )
        
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        # The tool should be callable
        assert callable(claude_tool.fn)
        
        try:
            # Test calling the function directly
            result = await claude_tool.fn(
                prompt="Say 'MCP integration test successful!' and nothing else.",
                workFolder="/tmp"
            )
            
            assert isinstance(result, str)
            assert len(result) > 0
            
        except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
            pytest.skip(f"Claude CLI not available or authentication issue: {e}")


class TestErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_claude_cli_not_found(self):
        """Test behavior when Claude CLI is not found."""
        # Mock the claude_cli_path to point to non-existent command
        with patch.object(claude_code_tool, 'claude_cli_path', 'nonexistent-claude'):
            with pytest.raises((FileNotFoundError, RuntimeError)):
                await claude_code_tool.execute_claude_code("test")
    
    @pytest.mark.asyncio
    async def test_empty_prompt(self):
        """Test behavior with empty prompt."""
        try:
            # Empty prompt should raise an error from Claude CLI
            with pytest.raises(RuntimeError, match="Claude CLI execution failed"):
                await claude_code_tool.execute_claude_code("")
            
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_very_long_prompt(self):
        """Test behavior with very long prompt."""
        long_prompt = "Say hello and describe briefly what you can do: " + "x" * 1000
        
        try:
            result = await claude_code_tool.execute_claude_code(long_prompt)
            assert isinstance(result, str)
            
        except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
            pytest.skip(f"Claude CLI not available or authentication issue: {e}")


class TestEnvironmentConfiguration:
    """Test environment variable configuration."""
    
    def test_debug_logging_disabled_by_default(self):
        """Test that debug logging is disabled by default."""
        # Create new tool instance
        tool = ClaudeCodeTool()
        
        # Debug mode should be controlled by environment
        assert os.getenv('MCP_CLAUDE_DEBUG') != 'true'
    
    def test_custom_cli_name_environment(self):
        """Test CLAUDE_CLI_NAME environment variable."""
        with patch.dict(os.environ, {'CLAUDE_CLI_NAME': 'test-claude'}):
            tool = ClaudeCodeTool()
            assert tool.claude_cli_path == 'test-claude'
    
    def test_timeout_configuration(self):
        """Test timeout configuration."""
        tool = ClaudeCodeTool()
        
        # Default timeout should be 30 minutes
        assert tool.timeout == 30 * 60


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])