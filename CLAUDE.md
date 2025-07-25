# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VibeCode is a one-command MCP (Model Context Protocol) server for Claude-Code that provides automatic persistent domains and OAuth 2.1 authentication. The project creates secure tunnels using Cloudflare to expose local MCP servers to the internet, enabling remote access to Claude-Code functionality.

## Core Architecture

### Main Components

- **CLI Module** (`vibecode/cli.py`): Primary interface providing `vibecode start` command with intelligent tunnel management
- **OAuth Provider** (`vibecode/oauth.py`): OAuth 2.1 implementation with Dynamic Client Registration (DCR) and PKCE support
- **Authenticated Server** (`vibecode/server.py`): FastAPI wrapper that combines MCP server with OAuth authentication middleware
- **Package Structure**: Two parallel directories (`vibecode/` and `vibecode_pkg/`) for development and distribution

### Authentication Flow

The system implements OAuth 2.1 with these endpoints:
- `/.well-known/oauth-authorization-server` - Server metadata
- `/register` - Dynamic client registration
- `/authorize` - Authorization with PKCE
- `/token` - Token exchange

### Tunnel Strategy

Automatic tunnel selection based on authentication status:
1. **Persistent tunnels**: Creates stable `vibecode-{timestamp}.cfargotunnel.com` domains when authenticated
2. **Quick tunnels**: Falls back to random `*.trycloudflare.com` domains
3. **Local mode**: `--no-tunnel` for development

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
```

### Testing
```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_integration.py::test_vibecode_local_mode

# Test CLI directly
python -m vibecode.cli --help
python -m vibecode.cli start --help
```

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