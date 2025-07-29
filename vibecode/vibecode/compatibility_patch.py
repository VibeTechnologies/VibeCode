"""Compatibility patch for MCP library issues."""

import sys
from typing import Any

def patch_mcp_imports():
    """Patch MCP imports to handle compatibility issues."""
    try:
        import mcp.types
        
        # Check if McpError is missing from mcp
        if not hasattr(mcp, 'McpError'):
            # Create a compatibility alias
            # Use JSONRPCError from mcp.types if available
            if hasattr(mcp.types, 'JSONRPCError'):
                mcp.McpError = mcp.types.JSONRPCError
            else:
                # Create a basic error class as fallback
                class McpError(Exception):
                    """MCP Error (compatibility)"""
                    pass
                mcp.McpError = McpError
        
        return True
    except ImportError as e:
        print(f"Warning: Could not patch MCP imports: {e}")
        return False

# Apply the patch on import
patch_mcp_imports()