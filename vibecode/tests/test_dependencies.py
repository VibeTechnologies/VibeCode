"""Test that all dependencies can be imported correctly."""

import pytest


def test_basic_imports():
    """Test that basic dependencies can be imported."""
    try:
        import fastapi
        import uvicorn
        import pydantic
        import httpx
        import requests
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import basic dependency: {e}")


def test_mcp_dependency():
    """Test MCP dependency import."""
    try:
        from mcp_claude_code.server import ClaudeCodeServer
        assert ClaudeCodeServer is not None
    except ImportError as e:
        pytest.skip(f"MCP dependency not available: {e}")


def test_oauth_dependencies():
    """Test OAuth-related dependencies."""
    try:
        from jose import jwt
        import secrets
        import hashlib
        import base64
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import OAuth dependency: {e}")


def test_vibecode_imports():
    """Test that vibecode modules can be imported."""
    try:
        from vibecode.oauth import OAuthProvider
        from vibecode.server import AuthenticatedMCPServer
        assert OAuthProvider is not None
        assert AuthenticatedMCPServer is not None
    except ImportError as e:
        pytest.fail(f"Failed to import vibecode modules: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])