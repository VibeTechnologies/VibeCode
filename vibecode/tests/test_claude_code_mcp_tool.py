"""Specific integration tests for the claude_code MCP tool registration and functionality."""

import asyncio
import os
import tempfile
from pathlib import Path
import pytest
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from vibecode.server import AuthenticatedMCPServer


class TestClaudeCodeMCPTool:
    """Test the claude_code tool as registered in the MCP server."""
    
    @pytest.fixture
    def server(self):
        """Create a VibeCode server instance for testing."""
        return AuthenticatedMCPServer(
            name='test-claude-code-mcp',
            allowed_paths=['/tmp', str(Path.cwd())],
            enable_agent_tool=True
        )
    
    def test_claude_code_tool_registration(self, server):
        """Test that claude_code tool is properly registered."""
        tools = server.mcp_server.mcp._tool_manager._tools
        
        # Verify claude_code tool exists
        assert 'claude_code' in tools
        
        # Get the tool
        claude_tool = tools['claude_code']
        
        # Verify tool properties
        assert claude_tool is not None
        assert hasattr(claude_tool, 'fn')
        assert callable(claude_tool.fn)
        
        # Check tool name
        assert hasattr(claude_tool, 'name')
        assert claude_tool.name == 'claude_code'
    
    def test_claude_code_tool_signature(self, server):
        """Test that claude_code tool has correct function signature."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        # Get function signature
        import inspect
        sig = inspect.signature(claude_tool.fn)
        params = list(sig.parameters.keys())
        
        # Should have prompt (required) and workFolder (optional)
        assert 'prompt' in params
        assert 'workFolder' in params
        
        # Check parameter defaults
        assert sig.parameters['workFolder'].default is None
    
    def test_claude_code_tool_docstring(self, server):
        """Test that claude_code tool has proper documentation."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        # Should have comprehensive docstring
        docstring = claude_tool.fn.__doc__
        assert docstring is not None
        assert 'Claude Code Agent' in docstring
        assert 'File ops' in docstring
        assert 'Git' in docstring
        assert 'Terminal' in docstring
        assert 'workFolder' in docstring
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_basic_execution(self, server):
        """Test basic execution of claude_code tool through MCP."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        try:
            # Test basic execution
            result = await claude_tool.fn(
                prompt="Say 'Hello from claude_code MCP tool test!' and nothing else.",
                workFolder=None
            )
            
            # Verify result
            assert isinstance(result, str)
            assert len(result) > 0
            assert 'Hello' in result or 'hello' in result.lower()
            
        except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
            pytest.skip(f"Claude CLI not available or authentication issue: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_with_work_folder(self, server):
        """Test claude_code tool execution with working directory."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Test with working directory
                result = await claude_tool.fn(
                    prompt="Tell me what directory I'm currently in. Don't create any files.",
                    workFolder=temp_dir
                )
                
                # Verify result
                assert isinstance(result, str)
                assert len(result) > 0
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_file_operations(self, server):
        """Test claude_code tool file operation capabilities."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test file
            test_file = Path(temp_dir) / "sample.txt"
            test_file.write_text("Hello World\nThis is a test file.\n")
            
            try:
                # Test file analysis
                result = await claude_tool.fn(
                    prompt="List and describe the files in the current directory. What's in sample.txt? Don't modify anything.",
                    workFolder=temp_dir
                )
                
                # Verify result mentions the file
                assert isinstance(result, str)
                assert len(result) > 0
                assert 'sample.txt' in result or 'sample' in result.lower()
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_code_analysis(self, server):
        """Test claude_code tool code analysis capabilities."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a Python file
            py_file = Path(temp_dir) / "example.py"
            py_file.write_text("""
def calculate_sum(a, b):
    \"\"\"Calculate the sum of two numbers.\"\"\"
    return a + b

def main():
    result = calculate_sum(5, 3)
    print(f"The sum is: {result}")

if __name__ == "__main__":
    main()
""")
            
            try:
                # Test code analysis
                result = await claude_tool.fn(
                    prompt="Analyze the Python code in this directory. What functions are defined? Don't modify anything.",
                    workFolder=temp_dir
                )
                
                # Verify result mentions the functions
                assert isinstance(result, str)
                assert len(result) > 0
                assert 'calculate_sum' in result or 'main' in result
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_error_handling(self, server):
        """Test claude_code tool error handling."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        # Test with empty prompt - should raise an error
        with pytest.raises(Exception):  # Could be RuntimeError or others
            await claude_tool.fn(prompt="", workFolder=None)
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_parameter_validation(self, server):
        """Test claude_code tool parameter validation."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        # Test that function accepts parameters correctly
        try:
            # Test with only required parameter
            result = await claude_tool.fn(prompt="Say hello")
            assert isinstance(result, str)
            
            # Test with both parameters
            result = await claude_tool.fn(
                prompt="Say hello", 
                workFolder="/tmp"
            )
            assert isinstance(result, str)
            
        except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
            pytest.skip(f"Claude CLI not available: {e}")
    
    def test_claude_code_tool_in_expected_tools_list(self, server):
        """Test that claude_code is in the expected tools list."""
        tools = server.mcp_server.mcp._tool_manager._tools
        
        expected_tools = [
            'read', 'write', 'edit', 'multi_edit',
            'directory_tree', 'grep', 'content_replace', 'grep_ast',
            'notebook_read', 'notebook_edit', 'run_command',
            'dispatch_agent', 'todo_read', 'todo_write',
            'think', 'batch', 'claude_code'
        ]
        
        for tool_name in expected_tools:
            assert tool_name in tools, f"Expected tool '{tool_name}' not found"
        
        # Verify claude_code is the 17th tool
        assert len(tools) == 17
        assert 'claude_code' in tools
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_multi_step_capability(self, server):
        """Test claude_code tool multi-step operation capability."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Test multi-step prompt
                result = await claude_tool.fn(
                    prompt="""Please do the following steps:
1. List the current directory contents
2. Tell me how many files are in the directory
3. Explain what type of directory this appears to be
Don't create or modify any files.""",
                    workFolder=temp_dir
                )
                
                # Verify multi-step response
                assert isinstance(result, str)
                assert len(result) > 0
                # Should contain references to steps or analysis
                assert any(word in result.lower() for word in ['directory', 'files', 'empty', 'contents'])
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")


class TestClaudeCodeMCPToolIntegration:
    """Test integration between claude_code tool and other MCP functionality."""
    
    def test_claude_code_tool_coexistence_with_other_tools(self):
        """Test that claude_code tool works alongside other MCP tools."""
        server = AuthenticatedMCPServer(
            name='test-coexistence',
            allowed_paths=['/tmp'],
            enable_agent_tool=True
        )
        
        tools = server.mcp_server.mcp._tool_manager._tools
        
        # Verify claude_code exists alongside other tools
        assert 'claude_code' in tools
        assert 'read' in tools  # Original mcp-claude-code tool
        assert 'write' in tools  # Original mcp-claude-code tool
        assert 'run_command' in tools  # Original mcp-claude-code tool
        
        # Verify no conflicts
        assert len(tools) == 17  # 16 original + 1 claude_code
        
        # Verify each tool is distinct
        claude_tool = tools['claude_code']
        read_tool = tools['read']
        
        assert claude_tool != read_tool
        assert claude_tool.fn != read_tool.fn
    
    @pytest.mark.asyncio
    async def test_claude_code_tool_vs_run_command_tool(self):
        """Test difference between claude_code and run_command tools."""
        server = AuthenticatedMCPServer(
            name='test-tool-comparison',
            allowed_paths=['/tmp'],
            enable_agent_tool=True
        )
        
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        run_command_tool = tools['run_command']
        
        # Verify they are different tools
        assert claude_tool != run_command_tool
        assert claude_tool.fn != run_command_tool.fn
        
        # Verify different signatures
        import inspect
        claude_sig = inspect.signature(claude_tool.fn)
        run_command_sig = inspect.signature(run_command_tool.fn)
        
        claude_params = set(claude_sig.parameters.keys())
        run_command_params = set(run_command_sig.parameters.keys())
        
        # Should have different parameter sets
        assert claude_params != run_command_params
        assert 'prompt' in claude_params
        assert 'workFolder' in claude_params


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])