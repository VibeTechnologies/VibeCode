"""Focused integration test for claude_code tool creating a Python Hello World application."""

import asyncio
import os
import tempfile
from pathlib import Path
import pytest
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from vibecode.server import AuthenticatedMCPServer


class TestClaudeCodeHelloWorld:
    """Test claude_code tool creating a Python Hello World application."""
    
    @pytest.fixture
    def server(self):
        """Create a VibeCode server instance for testing."""
        return AuthenticatedMCPServer(
            name='test-claude-code-hello-world',
            allowed_paths=['/tmp', str(Path.cwd())],
            enable_agent_tool=True
        )
    
    @pytest.mark.asyncio
    async def test_claude_code_create_hello_world_app(self, server):
        """Test claude_code tool creating a complete Python Hello World application."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Ask claude_code to create a Python Hello World app
                result = await claude_tool.fn(
                    prompt="""Create a Python Hello World application with the following requirements:
1. Create a file called 'hello_world.py'
2. The file should contain a main function that prints "Hello, World!"
3. Include proper Python structure with if __name__ == "__main__": guard
4. Add a docstring to explain what the program does
5. Make the file executable and test that it runs correctly

Please create the file and confirm it works.""",
                    workFolder=temp_dir
                )
                
                # Verify the claude_code tool responded
                assert isinstance(result, str)
                assert len(result) > 0
                print(f"\n🔍 Claude Code Response:")
                print("=" * 60)
                print(result)
                print("=" * 60)
                
                # Check if the file was created
                hello_world_file = Path(temp_dir) / "hello_world.py"
                assert hello_world_file.exists(), f"hello_world.py was not created in {temp_dir}"
                
                # Read and validate the file content
                content = hello_world_file.read_text()
                print(f"\n📄 Created file content:")
                print("-" * 40)
                print(content)
                print("-" * 40)
                
                # Validate file structure
                assert "def main(" in content or "def main():" in content, "File missing main function"
                assert 'print(' in content and 'Hello' in content, "File missing Hello World print statement"
                assert 'if __name__ == "__main__":' in content, "File missing main guard"
                assert '"""' in content or "'''" in content, "File missing docstring"
                
                # Test that the Python file actually runs
                try:
                    process_result = subprocess.run(
                        [sys.executable, str(hello_world_file)],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=temp_dir
                    )
                    
                    print(f"\n🚀 Python execution results:")
                    print(f"   Return code: {process_result.returncode}")
                    print(f"   Stdout: '{process_result.stdout.strip()}'")
                    print(f"   Stderr: '{process_result.stderr.strip()}'")
                    
                    assert process_result.returncode == 0, f"Python file failed to run: {process_result.stderr}"
                    assert "Hello" in process_result.stdout, f"Output missing 'Hello': {process_result.stdout}"
                    
                    print(f"✅ SUCCESS: Python execution output: '{process_result.stdout.strip()}'")
                    
                except subprocess.TimeoutExpired:
                    pytest.fail("Python file execution timed out")
                except Exception as e:
                    pytest.fail(f"Failed to execute Python file: {e}")
                
                # Additional validation
                print(f"\n📊 Validation Summary:")
                print(f"   ✅ File created: {hello_world_file.name}")
                print(f"   ✅ File size: {len(content)} characters")
                print(f"   ✅ Has main function: {'def main(' in content or 'def main():' in content}")
                print(f"   ✅ Has main guard: {'if __name__ == \"__main__\":' + ';' in content}")
                print(f"   ✅ Has docstring: {'\"\"\"' in content or \"'''\" in content}")
                print(f"   ✅ Executable: {process_result.returncode == 0}")
                print(f"   ✅ Correct output: {'Hello' in process_result.stdout}")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available or authentication issue: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_simple_task(self, server):
        """Test claude_code tool with a simple file creation task."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Simple task: create a greeting file
                result = await claude_tool.fn(
                    prompt="""Create a simple Python file called 'greetings.py' that:
1. Defines a function called 'say_hello' that takes a name parameter
2. The function should return a greeting message with the name
3. Include a simple test in the main section that calls the function

Keep it simple and make sure it works.""",
                    workFolder=temp_dir
                )
                
                assert isinstance(result, str)
                assert len(result) > 0
                
                # Check file creation
                greetings_file = Path(temp_dir) / "greetings.py"
                assert greetings_file.exists(), "greetings.py was not created"
                
                # Validate content
                content = greetings_file.read_text()
                assert "def say_hello(" in content, "Missing say_hello function"
                assert "return" in content, "Function missing return statement"
                
                # Test execution
                process_result = subprocess.run(
                    [sys.executable, str(greetings_file)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                assert process_result.returncode == 0, f"Script failed: {process_result.stderr}"
                print(f"✅ Greetings script output: {process_result.stdout.strip()}")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_file_analysis(self, server):
        """Test claude_code tool analyzing existing files."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a sample Python file first
            sample_file = Path(temp_dir) / "sample.py"
            sample_content = '''def fibonacci(n):
    """Calculate the nth Fibonacci number."""
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

if __name__ == "__main__":
    for i in range(10):
        print(f"fib({i}) = {fibonacci(i)}")
'''
            sample_file.write_text(sample_content)
            
            try:
                # Ask claude_code to analyze the file
                result = await claude_tool.fn(
                    prompt="""Analyze the Python file 'sample.py' in this directory:
1. Describe what the code does
2. Identify any potential issues or improvements
3. Explain the algorithm used
4. Don't modify the file, just analyze it

Provide a clear analysis of the code.""",
                    workFolder=temp_dir
                )
                
                assert isinstance(result, str)
                assert len(result) > 0
                print(f"\n🔍 Code Analysis Result:")
                print("=" * 50)
                print(result)
                print("=" * 50)
                
                # Verify analysis mentions key aspects
                result_lower = result.lower()
                assert 'fibonacci' in result_lower, "Analysis should mention Fibonacci"
                assert 'function' in result_lower or 'algorithm' in result_lower, "Analysis should discuss the function/algorithm"
                
                # Verify file wasn't modified
                current_content = sample_file.read_text()
                assert current_content == sample_content, "File was unexpectedly modified"
                
                print("✅ Code analysis completed successfully without modifying the file")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])