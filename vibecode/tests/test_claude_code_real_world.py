"""Real-world integration tests for claude_code tool with actual file creation tasks."""

import asyncio
import os
import tempfile
from pathlib import Path
import pytest
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from vibecode.server import AuthenticatedMCPServer


class TestClaudeCodeRealWorld:
    """Test claude_code tool with real-world tasks like creating Python applications."""
    
    @pytest.fixture
    def server(self):
        """Create a VibeCode server instance for testing."""
        return AuthenticatedMCPServer(
            name='test-claude-code-real-world',
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
5. Make sure the file is executable and runs correctly

Please create the file and then test that it works by running it.""",
                    workFolder=temp_dir
                )
                
                # Verify the claude_code tool responded
                assert isinstance(result, str)
                assert len(result) > 0
                print(f"\n🔍 Claude Code Response:\n{result}\n")
                
                # Check if the file was created
                hello_world_file = Path(temp_dir) / "hello_world.py"
                assert hello_world_file.exists(), f"hello_world.py was not created in {temp_dir}"
                
                # Read and validate the file content
                content = hello_world_file.read_text()
                print(f"📄 Created file content:\n{content}\n")
                
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
                        timeout=10
                    )
                    
                    assert process_result.returncode == 0, f"Python file failed to run: {process_result.stderr}"
                    assert "Hello" in process_result.stdout, f"Output missing 'Hello': {process_result.stdout}"
                    print(f"✅ Python execution output: {process_result.stdout.strip()}")
                    
                except subprocess.TimeoutExpired:
                    pytest.fail("Python file execution timed out")
                except Exception as e:
                    pytest.fail(f"Failed to execute Python file: {e}")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available or authentication issue: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_create_and_modify_python_app(self, server):
        """Test claude_code tool creating and then modifying a Python application."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Step 1: Create initial Python app
                result1 = await claude_tool.fn(
                    prompt="""Create a simple Python calculator app:
1. Create 'calculator.py' 
2. Include functions for add, subtract, multiply, divide
3. Include a main function that demonstrates each operation
4. Use proper Python structure and docstrings""",
                    workFolder=temp_dir
                )
                
                assert isinstance(result1, str)
                print(f"\n🔍 Step 1 - Create calculator:\n{result1[:200]}...\n")
                
                # Verify calculator was created
                calc_file = Path(temp_dir) / "calculator.py"
                assert calc_file.exists(), "calculator.py was not created"
                
                initial_content = calc_file.read_text()
                assert "def add(" in initial_content, "Missing add function"
                assert "def subtract(" in initial_content, "Missing subtract function"
                
                # Step 2: Modify the app to add more features
                result2 = await claude_tool.fn(
                    prompt="""Modify the calculator.py file to add these features:
1. Add a power function (exponentiation)
2. Add input validation to prevent division by zero
3. Add a simple command-line interface that asks user for operations
4. Test that the enhanced calculator works correctly""",
                    workFolder=temp_dir
                )
                
                assert isinstance(result2, str)
                print(f"\n🔍 Step 2 - Enhance calculator:\n{result2[:200]}...\n")
                
                # Verify modifications
                modified_content = calc_file.read_text()
                assert len(modified_content) > len(initial_content), "File was not expanded"
                assert "power" in modified_content.lower() or "**" in modified_content, "Missing power functionality"
                
                # Test that the modified file is valid Python
                try:
                    compile(modified_content, calc_file, 'exec')
                    print("✅ Modified Python file compiles successfully")
                except SyntaxError as e:
                    pytest.fail(f"Modified Python file has syntax errors: {e}")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_create_project_structure(self, server):
        """Test claude_code tool creating a complete project structure."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                result = await claude_tool.fn(
                    prompt="""Create a complete Python project structure for a simple web scraper:
1. Create a main directory structure with:
   - src/ directory for source code
   - tests/ directory for tests
   - requirements.txt file
   - README.md file
   - main.py as entry point
2. In src/, create a basic web scraper module (webscraper.py) that uses requests
3. Create a simple test file in tests/
4. Add appropriate content to README.md explaining the project
5. List all files created and their purposes""",
                    workFolder=temp_dir
                )
                
                assert isinstance(result, str)
                print(f"\n🔍 Project creation response:\n{result[:300]}...\n")
                
                # Verify project structure
                project_files = {
                    'src': Path(temp_dir) / 'src',
                    'tests': Path(temp_dir) / 'tests', 
                    'requirements.txt': Path(temp_dir) / 'requirements.txt',
                    'README.md': Path(temp_dir) / 'README.md',
                    'main.py': Path(temp_dir) / 'main.py',
                    'webscraper.py': Path(temp_dir) / 'src' / 'webscraper.py'
                }
                
                # Check that directories and files exist
                for name, path in project_files.items():
                    if name in ['src', 'tests']:
                        assert path.is_dir(), f"Directory {name} was not created"
                    else:
                        assert path.is_file(), f"File {name} was not created at {path}"
                
                # Validate file contents
                readme_content = project_files['README.md'].read_text()
                assert len(readme_content) > 50, "README.md is too short"
                assert "scraper" in readme_content.lower(), "README missing project description"
                
                requirements_content = project_files['requirements.txt'].read_text()
                assert "requests" in requirements_content, "requirements.txt missing requests dependency"
                
                webscraper_content = project_files['webscraper.py'].read_text()
                assert "import requests" in webscraper_content or "requests" in webscraper_content, "webscraper.py missing requests import"
                
                print("✅ Complete project structure created successfully")
                
                # List all created files for verification
                all_files = list(Path(temp_dir).rglob('*'))
                file_list = [str(f.relative_to(temp_dir)) for f in all_files if f.is_file()]
                print(f"📁 Created files: {sorted(file_list)}")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_debug_and_fix_code(self, server):
        """Test claude_code tool debugging and fixing broken Python code."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a buggy Python file first
            buggy_file = Path(temp_dir) / "buggy_code.py"
            buggy_content = '''
def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)  # Bug: division by zero if empty list

def main():
    test_numbers = [1, 2, 3, 4, 5]
    empty_list = []
    
    print("Average of test_numbers:", calculate_average(test_numbers))
    print("Average of empty_list:", calculate_average(empty_list))  # This will crash
    
    # Syntax error below
    print("This line has a syntax error"
    print("Missing closing parenthesis above")  # Syntax error

if __name__ == "__main__":
    main()
'''
            buggy_file.write_text(buggy_content)
            
            try:
                result = await claude_tool.fn(
                    prompt="""I have a buggy Python file called 'buggy_code.py' in this directory. Please:
1. Analyze the code and identify all bugs and issues
2. Fix the division by zero error
3. Fix the syntax error
4. Add proper error handling and input validation
5. Test that the fixed code runs without errors
6. Explain what was wrong and how you fixed it""",
                    workFolder=temp_dir
                )
                
                assert isinstance(result, str)
                print(f"\n🔍 Debug and fix response:\n{result[:400]}...\n")
                
                # Verify the file was modified
                fixed_content = buggy_file.read_text()
                assert fixed_content != buggy_content, "File was not modified"
                
                # Check that syntax errors are fixed
                try:
                    compile(fixed_content, buggy_file, 'exec')
                    print("✅ Fixed Python file compiles successfully")
                except SyntaxError as e:
                    pytest.fail(f"Fixed file still has syntax errors: {e}")
                
                # Test that the fixed file runs without crashing
                try:
                    process_result = subprocess.run(
                        [sys.executable, str(buggy_file)],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    # Should not crash with division by zero anymore
                    print(f"🔍 Fixed code output:\n{process_result.stdout}")
                    print(f"🔍 Fixed code errors:\n{process_result.stderr}")
                    
                    # The program should handle the empty list gracefully now
                    assert process_result.returncode == 0, f"Fixed code still crashes: {process_result.stderr}"
                    
                    print("✅ Fixed code runs successfully without crashing")
                    
                except subprocess.TimeoutExpired:
                    pytest.fail("Fixed code execution timed out")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")
    
    @pytest.mark.asyncio
    async def test_claude_code_git_workflow(self, server):
        """Test claude_code tool performing Git operations on created files."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                result = await claude_tool.fn(
                    prompt="""Perform a complete Git workflow:
1. Initialize a new Git repository
2. Create a simple Python 'hello.py' file
3. Create a .gitignore file for Python projects
4. Add all files to Git
5. Make an initial commit with message "Initial commit: Add hello.py"
6. Check the Git status and log to confirm everything worked
7. Report the final status of the repository""",
                    workFolder=temp_dir
                )
                
                assert isinstance(result, str)
                print(f"\n🔍 Git workflow response:\n{result[:400]}...\n")
                
                # Verify Git repository was created
                git_dir = Path(temp_dir) / '.git'
                assert git_dir.exists(), "Git repository was not initialized"
                
                # Verify files were created
                hello_file = Path(temp_dir) / 'hello.py'
                gitignore_file = Path(temp_dir) / '.gitignore'
                
                assert hello_file.exists(), "hello.py was not created"
                assert gitignore_file.exists(), ".gitignore was not created"
                
                # Verify .gitignore has Python-specific content
                gitignore_content = gitignore_file.read_text()
                assert '__pycache__' in gitignore_content or '*.pyc' in gitignore_content, ".gitignore missing Python patterns"
                
                # Verify Git commit was made
                try:
                    git_log = subprocess.run(
                        ['git', 'log', '--oneline'],
                        cwd=temp_dir,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    assert git_log.returncode == 0, "Git log failed"
                    assert len(git_log.stdout.strip()) > 0, "No commits found"
                    assert "Initial commit" in git_log.stdout or "hello.py" in git_log.stdout, "Commit message not found"
                    
                    print(f"✅ Git log shows: {git_log.stdout.strip()}")
                    
                except subprocess.TimeoutExpired:
                    pytest.fail("Git log command timed out")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")


class TestClaudeCodeComplexTasks:
    """Test claude_code tool with more complex, multi-step tasks."""
    
    @pytest.fixture
    def server(self):
        return AuthenticatedMCPServer(
            name='test-claude-code-complex',
            allowed_paths=['/tmp'],
            enable_agent_tool=True
        )
    
    @pytest.mark.asyncio
    async def test_claude_code_create_api_with_tests(self, server):
        """Test claude_code creating a REST API with tests."""
        tools = server.mcp_server.mcp._tool_manager._tools
        claude_tool = tools['claude_code']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                result = await claude_tool.fn(
                    prompt="""Create a simple REST API project with tests:
1. Create a Flask API (app.py) with endpoints:
   - GET /health (returns {"status": "healthy"})
   - GET /users (returns list of sample users)
   - POST /users (accepts user data)
2. Create requirements.txt with necessary dependencies
3. Create test_app.py with unit tests for all endpoints
4. Create a simple README.md with usage instructions
5. Verify all files are created and contain appropriate content""",
                    workFolder=temp_dir
                )
                
                assert isinstance(result, str)
                print(f"\n🔍 API creation response:\n{result[:300]}...\n")
                
                # Verify all expected files exist
                expected_files = ['app.py', 'requirements.txt', 'test_app.py', 'README.md']
                for filename in expected_files:
                    file_path = Path(temp_dir) / filename
                    assert file_path.exists(), f"{filename} was not created"
                
                # Verify app.py contains Flask code
                app_content = (Path(temp_dir) / 'app.py').read_text()
                assert 'from flask import' in app_content or 'import flask' in app_content, "app.py missing Flask import"
                assert '/health' in app_content, "app.py missing health endpoint"
                assert '/users' in app_content, "app.py missing users endpoint"
                
                # Verify requirements.txt contains Flask
                req_content = (Path(temp_dir) / 'requirements.txt').read_text()
                assert 'flask' in req_content.lower(), "requirements.txt missing Flask"
                
                # Verify test file contains test functions
                test_content = (Path(temp_dir) / 'test_app.py').read_text()
                assert 'def test_' in test_content, "test_app.py missing test functions"
                
                print("✅ Complete API project created successfully")
                
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
                pytest.skip(f"Claude CLI not available: {e}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])