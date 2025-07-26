"""Mock MCP server for testing when mcp-claude-code is not available."""

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json
import uuid
from typing import Dict, Any, AsyncGenerator


class MockClaudeCodeServer:
    """Mock MCP server for testing purposes."""
    
    def __init__(self, name: str = "mock-server", allowed_paths: list = None, enable_agent_tool: bool = False):
        self.name = name
        self.allowed_paths = allowed_paths or ["/"]
        self.enable_agent_tool = enable_agent_tool
        self.app = FastAPI(title=f"Mock {name}")
        self.mcp = MockMCP()  # Add mock MCP attribute
        self.mcp._sse_app = self.app  # Set _sse_app for compatibility
        self.setup_routes()
    
    def setup_routes(self):
        """Setup mock MCP routes."""
        
        @self.app.get("/health")
        async def health():
            return {"status": "healthy", "server": self.name, "mock": True}
        
        # Add a catch-all route to debug what's happening
        @self.app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
        async def handle_all_requests(request: Request):
            """Handle all requests for debugging."""
            print(f"🔍 Mock app received {request.method} request to: {request.url.path}")
            print(f"🔍 Mock app request headers: {dict(request.headers)}")
            print(f"🔍 Mock app full URL: {request.url}")
            
            if request.method == "POST":
                try:
                    request_data = await request.json()
                    print(f"🔍 Mock app request data: {request_data}")
                    return await self.handle_mcp_message(request_data)
                except Exception as e:
                    print(f"🔍 Mock app error processing request: {e}")
                    return {"error": str(e)}
            else:
                return {"status": "MCP SSE endpoint", "server": self.name, "method": request.method}
        
        @self.app.post("/")
        async def handle_mcp_root(request: Request):
            """Handle MCP messages at root path."""
            print(f"📍 ROOT: Mock app received POST request to: {request.url.path}")
            print(f"📍 ROOT: Mock app request method: {request.method}")
            print(f"📍 ROOT: Mock app request headers: {dict(request.headers)}")
            try:
                request_data = await request.json()
                print(f"📍 ROOT: Mock app request data: {request_data}")
                return await self.handle_mcp_message(request_data)
            except Exception as e:
                print(f"📍 ROOT: Mock app error processing request: {e}")
                return {"error": str(e)}
        
        @self.app.get("/")
        async def handle_mcp_root_get():
            """Handle GET requests to root path."""
            return {"status": "MCP SSE endpoint", "server": self.name}
        
        @self.app.post("/message")
        async def handle_message(request_data: Dict[str, Any]):
            """Handle MCP messages."""
            return await self.handle_mcp_message(request_data)
    
    async def handle_mcp_message(self, request_data: Dict[str, Any]):
        """Handle MCP message and return SSE response."""
        # Mock MCP response
        response = {
            "jsonrpc": "2.0",
            "id": request_data.get("id", str(uuid.uuid4())),
        }
        
        method = request_data.get("method", "")
        
        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "logging": {},
                    "tools": {
                        "listChanged": True
                    }
                },
                "serverInfo": {
                    "name": self.name,
                    "version": "1.0.0-mock"
                }
            }
        else:
            response["error"] = {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        
        # Return as SSE stream
        async def generate_sse():
            yield f"data: {json.dumps(response)}\n\n"
        
        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )


class MockMCP:
    """Mock MCP class to simulate mcp-claude-code interface."""
    
    def __init__(self):
        self._sse_app = None
        self._tools = {}
        self._tool_manager = MockToolManager()
    
    def sse_app(self):
        """Return the SSE app - must be a method like in real mcp-claude-code."""
        return self._sse_app
    
    def http_app(self):
        """Return the HTTP app - modern method replacing sse_app."""
        return self._sse_app
    
    def streamable_http_app(self):
        """Return the HTTP app - deprecated method for compatibility."""
        return self._sse_app
    
    def tool(self):
        """Mock tool decorator that registers functions."""
        def decorator(func):
            # Register the tool
            tool_name = func.__name__
            self._tools[tool_name] = MockTool(tool_name, func)
            # Add to tool manager as well for compatibility
            if hasattr(self._tool_manager, '_tools'):
                self._tool_manager._tools[tool_name] = self._tools[tool_name]
            return func
        return decorator


class MockToolManager:
    """Mock tool manager for testing."""
    
    def __init__(self):
        self._tools = {}


class MockTool:
    """Mock tool for testing."""
    
    def __init__(self, name: str, func):
        self.name = name
        self.fn = func


class MockMCPRuntime:
    """Mock MCP runtime with run method."""
    
    def run(self, transport: str = "sse", host: str = "0.0.0.0", port: int = 8300, path: str = "/"):
        """Mock run method."""
        if transport == "sse":
            import uvicorn
            from fastapi import FastAPI
            
            app = FastAPI()
            
            @app.get("/health")
            async def health():
                return {"status": "healthy", "mock": True}
            
            uvicorn.run(app, host=host, port=port)
        else:
            raise NotImplementedError(f"Transport {transport} not supported in mock")


# Monkey patch for testing
def patch_mcp_import():
    """Patch the mcp-claude-code import for testing."""
    import sys
    from types import ModuleType
    
    # Create mock module
    mock_module = ModuleType("mcp_claude_code")
    mock_server_module = ModuleType("mcp_claude_code.server")
    
    # Add mock classes
    mock_server_module.ClaudeCodeServer = MockClaudeCodeServer
    mock_module.server = mock_server_module
    
    # Add to sys.modules
    sys.modules["mcp_claude_code"] = mock_module
    sys.modules["mcp_claude_code.server"] = mock_server_module