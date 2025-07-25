"""
VibeCode - MCP server for Claude-Code with OAuth authentication and automatic Cloudflare tunneling.
"""

__version__ = "0.1.0"

from .server import AuthenticatedMCPServer
from .oauth import OAuthProvider

__all__ = ["AuthenticatedMCPServer", "OAuthProvider"]