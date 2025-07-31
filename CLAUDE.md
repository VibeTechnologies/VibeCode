# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VibeCode is a one-command MCP (Model Context Protocol) server that provides automatic persistent domains and OAuth 2.1 authentication. The project creates secure tunnels using Cloudflare to expose local MCP servers to the internet, enabling remote access to development tools including the full mcp-claude-code toolkit plus native Claude Code CLI integration.

## Core Architecture

### Main Components

- **CLI Module** (`vibecode/cli.py`): Primary interface providing `vibecode start` command with intelligent tunnel management
- **OAuth Provider** (`vibecode/oauth.py`): OAuth 2.1 implementation with Dynamic Client Registration (DCR) and PKCE support
- **Authenticated Server** (`vibecode/server.py`): FastAPI wrapper that combines MCP server with OAuth authentication middleware
- **Claude Code Integration** (`vibecode/claude_code_tool.py`): Native Claude Code CLI integration with permission bypass for seamless MCP access
- **Package Structure**: Two parallel directories (`vibecode/` and `vibecode_pkg/`) for development and distribution

### Authentication Flow

The system implements OAuth 2.1 with these endpoints:
- `/.well-known/oauth-authorization-server` - Server metadata
- `/register` - Dynamic client registration
- `/authorize` - Authorization with PKCE
- `/token` - Token exchange

### Tunnel Strategy

Automatic tunnel selection based on authentication status with persistence support:
1. **Persistent tunnels**: Creates stable `vibecode-{timestamp}.cfargotunnel.com` domains when authenticated
2. **Quick tunnels**: Falls back to random `*.trycloudflare.com` domains
3. **Local mode**: `--no-tunnel` for development
4. **Tunnel Persistence**: Automatically reuses existing tunnel processes across MCP server restarts

#### Tunnel Persistence Features

- **Process Tracking**: Saves tunnel process PID and URL to `.vibecode.json`
- **Smart Reuse**: Automatically detects and reuses running tunnel processes
- **Process Validation**: Checks if saved tunnel process is still alive before reuse
- **Graceful Fallback**: Creates new tunnel if existing process is not accessible
- **Manual Control**: Commands to check status (`vibecode tunnel status`) and stop tunnels (`vibecode tunnel stop`)
- **Configuration Options**: `--no-reuse` flag to force creation of new tunnels

### Available Tools

VibeCode exposes **17 powerful development tools** through the MCP protocol:

#### **File Operations**
- `read`, `write`, `edit`, `multi_edit` - File manipulation
- `directory_tree` - Directory structure visualization
- `grep`, `grep_ast`, `content_replace` - Code search and replacement

#### **Jupyter Support**
- `notebook_read`, `notebook_edit` - Jupyter notebook operations

#### **Shell & Commands**
- `run_command` - Execute shell commands in persistent sessions

#### **Task Management**
- `todo_read`, `todo_write` - Session task tracking

#### **Advanced Features**
- `dispatch_agent` - Sub-agent delegation for complex tasks
- `batch` - Batch multiple tool operations
- `think` - Structured reasoning tool

#### **🚀 Claude Code Integration**
- `claude_code` - **The flagship tool**: Full Claude Code CLI access with:
  - File operations, code analysis, Git workflows
  - Terminal command execution, web search
  - Multi-step automation, GitHub integration
  - Permission bypass (`--dangerously-skip-permissions`) for seamless operation

## Development Commands

### Installation and Setup
```bash
# Install in development mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Install cloudflared (required for tunnels)
brew install cloudflared
```

### Running the Server
```bash
# Start with persistent domain (requires cloudflare login)
vibecode start

# Start with temporary domain
vibecode start --quick

# Local development (no tunnel)
vibecode start --no-tunnel --port 8300

# Use specific tunnel
vibecode start --tunnel my-tunnel-name

# Tunnel management commands
vibecode tunnel status    # Check current tunnel status
vibecode tunnel stop      # Stop running tunnel
vibecode start --no-reuse # Force new tunnel (skip reuse)
```

### Testing

**IMPORTANT: ALWAYS RUN TESTS DURING DEVELOPMENT**
- Run tests between iterations to ensure nothing is broken
- MANDATORY: Always run the end-to-end test before marking any task as complete

```bash
# Run all integration tests (main test suite)
python -m pytest vibecode/tests/ -v

# Run core integration tests (faster)
python -m pytest vibecode/tests/test_integration.py -v

# Run end-to-end comprehensive test (REQUIRED before completing tasks)
python test_claude_code_integration.py

# Run specific test
pytest vibecode/tests/test_integration.py::test_vibecode_local_mode

# Test CLI directly
python -m vibecode.cli --help
python -m vibecode.cli start --help
```

**Test Running Policy:**
1. **Between iterations**: Run `python -m pytest vibecode/tests/test_integration.py -v` to verify core functionality
2. **Before task completion**: ALWAYS run `python test_claude_code_integration.py` for end-to-end validation
3. **Full test suite**: Use `python -m pytest vibecode/tests/ -v` for comprehensive testing

### Code Quality
```bash
# Format code
black vibecode/

# Check imports
isort vibecode/

# Lint
flake8 vibecode/

# Type checking
mypy vibecode/
```

## Key Implementation Details

### Cloudflared Integration

The system automatically detects cloudflared installation across multiple paths:
- `cloudflared` (in PATH)
- `/opt/homebrew/bin/cloudflared` (Apple Silicon)
- `/usr/local/bin/cloudflared` (Intel Mac)
- `/usr/bin/cloudflared` (Linux)

### Security Model

- **UUID Paths**: Each session generates unique UUID paths (`/{uuid}`) for security
- **OAuth Authentication**: Full OAuth 2.1 flow with PKCE for public clients
- **CORS Configuration**: Allows all origins (configure for production)
- **Token Validation**: JWT tokens with 1-hour expiration

### Server Architecture

The `AuthenticatedMCPServer` wraps the base `ClaudeCodeServer` with:
- FastAPI middleware for authentication
- OAuth endpoint mounting
- Health checks at `/health`
- Selective authentication (skips OAuth endpoints)

## Project Structure Notes

- **Dual Structure**: Both `vibecode/` and `vibecode_pkg/` contain similar code for development/distribution
- **Entry Point**: `vibecode.cli:main` is the main entry point defined in pyproject.toml
- **Dependencies**: Built on `mcp-claude-code`, FastAPI, uvicorn, and Cloudflare tooling
- **Python Version**: Requires Python 3.10+

## Common Development Patterns

- **Error Handling**: Graceful fallbacks from persistent to quick tunnels
- **Process Management**: Daemon threads for MCP server, subprocess management for tunnels
- **Configuration**: Environment-based with intelligent defaults
- **Logging**: stderr for tunnel output, stdout for user instructions
- **Testing**: Mandatory end-to-end testing before task completion to ensure system integrity

## Development Workflow Requirements

**CRITICAL: Testing is MANDATORY before completing any task**

1. **During Development**: Run integration tests between iterations
   ```bash
   python -m pytest vibecode/tests/test_integration.py -v
   ```

2. **Before Task Completion**: ALWAYS run the end-to-end test
   ```bash
   python test_claude_code_integration.py
   ```

3. **Task is NOT complete** until the E2E test passes successfully

This ensures that:
- Core MCP server functionality works
- Claude Code integration is intact  
- All 17 tools are properly exposed
- Server startup and communication protocols function correctly