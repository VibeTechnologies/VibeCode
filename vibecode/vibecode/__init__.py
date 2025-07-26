"""
VibeCode - MCP server for Claude-Code with OAuth authentication and automatic Cloudflare tunneling.
"""

# Suppress warnings at package level  
import warnings
import os

# Suppress all deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*class-based.*config.*deprecated.*")
warnings.filterwarnings("ignore", message=".*websockets.legacy.*deprecated.*")
warnings.filterwarnings("ignore", message=".*get_event_loop.*deprecated.*")

# Suppress Pydantic warnings
os.environ["PYDANTIC_DISABLE_WARNINGS"] = "1"

__version__ = "0.1.0"

from .server import AuthenticatedMCPServer
from .oauth import OAuthProvider

__all__ = ["AuthenticatedMCPServer", "OAuthProvider"]