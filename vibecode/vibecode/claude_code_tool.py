"""Claude Code integration tool for VibeCode MCP server."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ClaudeCodeTool:
    """Tool for executing Claude Code CLI with permission bypass."""
    
    def __init__(self):
        self.claude_cli_path = self._find_claude_cli()
        self.timeout = 30 * 60  # 30 minutes timeout
        
    def _find_claude_cli(self) -> str:
        """Find Claude CLI command/path using the same logic as steipete's implementation."""
        logger.debug("Attempting to find Claude CLI...")
        
        # Check for custom CLI name from environment variable
        custom_cli_name = os.getenv('CLAUDE_CLI_NAME')
        if custom_cli_name:
            logger.debug(f"Using custom Claude CLI name from CLAUDE_CLI_NAME: {custom_cli_name}")
            
            # If it's an absolute path, use it directly
            if os.path.isabs(custom_cli_name):
                logger.debug(f"CLAUDE_CLI_NAME is an absolute path: {custom_cli_name}")
                return custom_cli_name
            
            # If it contains path separators (relative paths), reject them
            if './' in custom_cli_name or '../' in custom_cli_name or '/' in custom_cli_name:
                raise ValueError(
                    f"Invalid CLAUDE_CLI_NAME: Relative paths are not allowed. "
                    f"Use either a simple name (e.g., 'claude') or an absolute path (e.g., '/tmp/claude-test')"
                )
        
        cli_name = custom_cli_name or 'claude'
        
        # Try local install path: ~/.claude/local/claude
        user_path = Path.home() / '.claude' / 'local' / 'claude'
        logger.debug(f"Checking for Claude CLI at local user path: {user_path}")
        
        if user_path.exists():
            logger.debug(f"Found Claude CLI at local user path: {user_path}")
            return str(user_path)
        else:
            logger.debug(f"Claude CLI not found at local user path: {user_path}")
        
        # Fallback to CLI name (PATH lookup)
        logger.debug(f'Falling back to "{cli_name}" command name, relying on PATH lookup')
        logger.warning(
            f'Claude CLI not found at ~/.claude/local/claude. '
            f'Falling back to "{cli_name}" in PATH. Ensure it is installed and accessible.'
        )
        return cli_name
    
    async def _spawn_async(
        self, 
        command: str, 
        args: list[str], 
        timeout: Optional[int] = None,
        cwd: Optional[str] = None
    ) -> Dict[str, str]:
        """Asynchronously spawn a process with timeout and error handling."""
        logger.debug(f"Running command: {command} {' '.join(args)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            # Wait for process with timeout
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout or self.timeout
            )
            
            stdout = stdout_data.decode('utf-8')
            stderr = stderr_data.decode('utf-8')
            
            logger.debug(f"Exit code: {process.returncode}")
            logger.debug(f"Stdout: {stdout.strip()}")
            if stderr:
                logger.debug(f"Stderr: {stderr.strip()}")
            
            if process.returncode != 0:
                error_msg = f"Command failed with exit code {process.returncode}"
                if stderr:
                    error_msg += f"\nStderr: {stderr.strip()}"
                if stdout:
                    error_msg += f"\nStdout: {stdout.strip()}"
                raise subprocess.CalledProcessError(process.returncode, command, error_msg)
            
            return {"stdout": stdout, "stderr": stderr}
            
        except asyncio.TimeoutError:
            logger.error(f"Command timed out after {timeout or self.timeout} seconds")
            raise TimeoutError(f"Claude CLI command timed out after {timeout or self.timeout} seconds")
        except FileNotFoundError as e:
            logger.error(f"Claude CLI not found: {e}")
            raise FileNotFoundError(
                f"Claude CLI not found at '{command}'. "
                f"Please ensure Claude CLI is installed and accessible. "
                f"Error: {e}"
            )
        except Exception as e:
            logger.error(f"Error executing Claude CLI: {e}")
            raise RuntimeError(f"Claude CLI execution failed: {e}")
    
    async def execute_claude_code(
        self, 
        prompt: str, 
        work_folder: Optional[str] = None
    ) -> str:
        """
        Execute Claude Code CLI with the given prompt.
        
        Args:
            prompt: The natural language prompt for Claude to execute
            work_folder: Optional working directory for execution
            
        Returns:
            The output from Claude CLI execution
        """
        logger.info(f"Executing Claude Code with prompt: {prompt[:100]}...")
        
        # Determine working directory
        effective_cwd = str(Path.home())  # Default to home directory
        
        if work_folder:
            resolved_cwd = os.path.abspath(work_folder)
            logger.debug(f"Specified workFolder: {work_folder}, Resolved to: {resolved_cwd}")
            
            if os.path.exists(resolved_cwd):
                effective_cwd = resolved_cwd
                logger.debug(f"Using workFolder as CWD: {effective_cwd}")
            else:
                logger.warning(f"Specified workFolder does not exist: {resolved_cwd}. Using default: {effective_cwd}")
        else:
            logger.debug(f"No workFolder provided, using default CWD: {effective_cwd}")
        
        # Prepare Claude CLI arguments
        claude_args = ['--dangerously-skip-permissions', '-p', prompt]
        logger.debug(f"Invoking Claude CLI: {self.claude_cli_path} {' '.join(claude_args)}")
        
        try:
            result = await self._spawn_async(
                self.claude_cli_path,
                claude_args,
                timeout=self.timeout,
                cwd=effective_cwd
            )
            
            # Return stdout content
            return result["stdout"]
            
        except Exception as e:
            logger.error(f"Error executing Claude CLI: {e}")
            raise
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """Get the MCP tool definition for the Claude Code tool."""
        return {
            "name": "claude_code",
            "description": """Claude Code Agent: Your versatile multi-modal assistant for code, file, Git, and terminal operations via Claude CLI. Use `workFolder` for contextual execution.

• File ops: Create, read, (fuzzy) edit, move, copy, delete, list files, analyze/ocr images, file content analysis
    └─ e.g., "Create /tmp/log.txt with 'system boot'", "Edit main.py to replace 'debug_mode = True' with 'debug_mode = False'", "List files in /src", "Move a specific section somewhere else"

• Code: Generate / analyse / refactor / fix
    └─ e.g. "Generate Python to parse CSV→JSON", "Find bugs in my_script.py"

• Git: Stage ▸ commit ▸ push ▸ tag (any workflow)
    └─ "Commit '/workspace/src/main.java' with 'feat: user auth' to develop."

• Terminal: Run any CLI cmd or open URLs
    └─ "npm run build", "Open https://developer.mozilla.org"

• Web search + summarise content on-the-fly

• Multi-step workflows  (Version bumps, changelog updates, release tagging, etc.)

• GitHub integration  Create PRs, check CI status

• Confused or stuck on an issue? Ask Claude Code for a second opinion, it might surprise you!

**Prompt tips**

1. Be concise, explicit & step-by-step for complex tasks. No need for niceties, this is a tool to get things done.
2. For multi-line text, write it to a temporary file in the project root, use that file, then delete it.
3. If you get a timeout, split the task into smaller steps.
4. **Seeking a second opinion/analysis**: If you're stuck or want advice, you can ask `claude_code` to analyze a problem and suggest solutions. Clearly state in your prompt that you are looking for analysis only and no actual file modifications should be made.
5. If workFolder is set to the project path, there is no need to repeat that path in the prompt and you can use relative paths for files.
6. Claude Code is really good at complex multi-step file operations and refactorings and faster than your native edit features.
7. Combine file operations, README updates, and Git commands in a sequence.
8. Claude can do much more, just ask it!""",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The detailed natural language prompt for Claude to execute."
                    },
                    "workFolder": {
                        "type": "string",
                        "description": "Mandatory when using file operations or referencing any file. The working directory for the Claude CLI execution. Must be an absolute path."
                    }
                },
                "required": ["prompt"]
            }
        }


# Create a global instance
claude_code_tool = ClaudeCodeTool()