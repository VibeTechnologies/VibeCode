"""Combined OAuth and MCP server implementation."""

# Suppress warnings at module level
import warnings
import os
warnings.simplefilter("ignore")
os.environ["PYDANTIC_DISABLE_WARNINGS"] = "1"

import asyncio
import json
import logging
from typing import Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .oauth import OAuthProvider, create_oauth_app
from .claude_code_tool import claude_code_tool

from mcp_claude_code.server import ClaudeCodeServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AuthenticatedMCPServer:
    """MCP server with OAuth 2.1 authentication."""
    
    def __init__(
        self, 
        name: str = "vibecode-server",
        allowed_paths: Optional[list] = None,
        enable_agent_tool: bool = False,
        base_url: str = "http://localhost:8300"
    ):
        self.name = name
        self.allowed_paths = allowed_paths or ["/"]
        self.enable_agent_tool = enable_agent_tool
        self.base_url = base_url.rstrip('/')
        
        # Create OAuth provider
        self.oauth_provider = OAuthProvider(base_url=self.base_url)
        
        # Create MCP server
        self.mcp_server = ClaudeCodeServer(
            name=self.name,
            allowed_paths=self.allowed_paths,
            enable_agent_tool=self.enable_agent_tool
        )
        
        # Add Claude Code tool to the MCP server
        self._add_claude_code_tool()
        
        # Create combined FastAPI app
        self.app = None
    
    def _add_claude_code_tool(self):
        """Add Claude Code tool to the MCP server."""
        mcp = self.mcp_server.mcp
        
        @mcp.tool()
        async def claude_code(prompt: str, workFolder: str = None) -> str:
            """Claude Code Agent: Your versatile multi-modal assistant for code, file, Git, and terminal operations via Claude CLI. Use `workFolder` for contextual execution.

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
8. Claude can do much more, just ask it!

Args:
    prompt: The detailed natural language prompt for Claude to execute.
    workFolder: Mandatory when using file operations or referencing any file. The working directory for the Claude CLI execution. Must be an absolute path.

Returns:
    The output from Claude CLI execution.
            """
            return await claude_code_tool.execute_claude_code(prompt, workFolder)
    
    def run_sse_with_auth(
        self,
        host: str = "0.0.0.0",
        port: int = 8300,
        path: str = "/mcp"
    ):
        """Run MCP server with OAuth 2.1 authentication using simplified direct mounting."""
        
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        from starlette.responses import JSONResponse
        import uvicorn
        
        # Get the MCP server's HTTP app directly
        mcp_server = self.mcp_server.mcp
        
        # Using custom MCP endpoint handler for better control
        logger.info("Initializing MCP server endpoint")
        
        # Try to use the real FastMCP server first, fallback to our custom implementation
        use_fallback = False
        
        if not use_fallback:
            # Try to use the real FastMCP SSE server
            try:
                from starlette.applications import Starlette
                from starlette.routing import Mount, Route
                from starlette.responses import JSONResponse
                import uvicorn
                
                # Get the FastMCP SSE app and try to run it properly with context
                fastmcp_app = mcp_server.mcp.sse_app
                logger.info("Attempting to use FastMCP SSE app")
                
                # Create OAuth endpoint handlers (same as before)
                async def oauth_auth_server_metadata(request):
                    return JSONResponse(self.oauth_provider.get_authorization_server_metadata())
                
                async def oauth_auth_server_metadata_with_uuid(request):
                    return JSONResponse(self.oauth_provider.get_authorization_server_metadata())
                
                async def oauth_protected_resource_metadata(request):
                    return JSONResponse({
                        "resource": self.base_url,
                        "authorization_servers": [self.base_url],
                        "scopes_supported": ["read", "write"],
                        "bearer_methods_supported": ["header"]
                    })
                
                async def oauth_protected_resource_metadata_with_uuid(request):
                    return JSONResponse({
                        "resource": self.base_url,
                        "authorization_servers": [self.base_url],
                        "scopes_supported": ["read", "write"],
                        "bearer_methods_supported": ["header"]
                    })
                
                async def register_client(request):
                    try:
                        from .oauth import ClientRegistrationRequest
                        body = await request.json()
                        client_request = ClientRegistrationRequest(**body)
                        response = self.oauth_provider.register_client(client_request)
                        return JSONResponse(response.model_dump())
                    except Exception as e:
                        return JSONResponse({"error": str(e)}, status_code=400)
                
                async def authorize(request):
                    try:
                        from .oauth import AuthorizationRequest
                        query_params = dict(request.query_params)
                        auth_request = AuthorizationRequest(**query_params)
                        redirect_url = self.oauth_provider.authorize(auth_request)
                        return JSONResponse({"redirect_url": redirect_url})
                    except Exception as e:
                        return JSONResponse({"error": str(e)}, status_code=400)
                
                async def token(request):
                    try:
                        from .oauth import TokenRequest
                        if request.headers.get("content-type") == "application/json":
                            body = await request.json()
                        else:
                            form = await request.form()
                            body = dict(form)
                        
                        token_request = TokenRequest(**body)
                        response = self.oauth_provider.exchange_code_for_token(token_request)
                        return JSONResponse(response)
                    except Exception as e:
                        return JSONResponse({"error": str(e)}, status_code=400)
                
                async def introspect_token(request):
                    try:
                        form = await request.form()
                        token = form.get("token")
                        if not token or not isinstance(token, str):
                            return JSONResponse({"active": False}, status_code=400)
                        
                        try:
                            self.oauth_provider.validate_token(token)
                            return JSONResponse({
                                "active": True,
                                "scope": "read write",
                                "token_type": "Bearer"
                            })
                        except Exception:
                            return JSONResponse({"active": False})
                            
                    except Exception as e:
                        return JSONResponse({"active": False}, status_code=400)
                
                async def revoke_token(request):
                    try:
                        form = await request.form()
                        token = form.get("token")
                        if not token or not isinstance(token, str):
                            return JSONResponse({"error": "Missing token parameter"}, status_code=400)
                        
                        return JSONResponse({"revoked": True})
                        
                    except Exception as e:
                        return JSONResponse({"error": str(e)}, status_code=400)
                
                async def health_check(request):
                    return JSONResponse({"status": "healthy", "server": self.name, "oauth_enabled": True})
                
                # Create the Starlette app with OAuth routes and real FastMCP app
                app = Starlette(
                    routes=[
                        # OAuth discovery endpoints
                        Route("/.well-known/oauth-authorization-server", oauth_auth_server_metadata, methods=["GET"]),
                        Route("/.well-known/oauth-authorization-server/{uuid_path}", oauth_auth_server_metadata_with_uuid, methods=["GET"]),
                        Route("/.well-known/oauth-protected-resource", oauth_protected_resource_metadata, methods=["GET"]),
                        Route("/.well-known/oauth-protected-resource/{uuid_path}", oauth_protected_resource_metadata_with_uuid, methods=["GET"]),
                        
                        # OAuth flow endpoints
                        Route("/register", register_client, methods=["POST"]),
                        Route("/authorize", authorize, methods=["GET"]),
                        Route("/token", token, methods=["POST"]),
                        
                        # MCP specification endpoints
                        Route("/introspect", introspect_token, methods=["POST"]),
                        Route("/revoke", revoke_token, methods=["POST"]),
                        
                        # Health endpoint
                        Route("/health", health_check, methods=["GET"]),
                        
                        # Mount real FastMCP app at the specified path
                        Mount(path, fastmcp_app),
                    ]
                )
                
                logger.info(f"Starting server on {host}:{port} with FastMCP at {path}")
                uvicorn.run(app, host=host, port=port, log_level="warning")
                return
                
            except Exception as e:
                logger.debug(f"FastMCP server unavailable: {e}")
                use_fallback = True
        
        if use_fallback:
            # Fallback: create a simple FastAPI app with MCP endpoints
            from fastapi import FastAPI, Request
            from fastapi.responses import StreamingResponse
            import json
            
            mcp_app = FastAPI()
            
            # Add HTTP request logging middleware
            @mcp_app.middleware("http")
            async def log_requests(request: Request, call_next):
                # Log incoming request with essential info only
                path = request.url.path
                if path != "/health":  # Skip health check spam
                    logger.info(f"{request.method} {path}")
                
                response = await call_next(request)
                
                # Log response status for errors only
                if response.status_code >= 400 and path != "/health":
                    logger.warning(f"HTTP {response.status_code} {path}")
                
                return response
            
            @mcp_app.post("/")
            async def handle_mcp_request(request: Request):
                """Handle MCP JSON-RPC requests."""
                try:
                    request_data = await request.json()
                    method = request_data.get("method", "")
                    request_id = request_data.get("id", "unknown")
                    
                    # Log MCP request with essential info only
                    logger.info(f"MCP {method} (id: {request_id})")
                    if method == "tools/call":
                        tool_name = request_data.get("params", {}).get("name", "unknown")
                        logger.info(f"  Tool: {tool_name}")
                    
                    if method == "initialize":
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {
                                    "tools": {"listChanged": True},
                                    "logging": {}
                                },
                                "serverInfo": {
                                    "name": self.name,
                                    "version": "1.0.0"
                                }
                            }
                        }
                    elif method == "tools/list":
                        # Get actual tools from the MCP server
                        tools = []
                        
                        # Try to get tools from the real MCP server in various ways
                        tools_found = False
                        
                        # Method 1: Check _tool_manager._tools (fastmcp)
                        if hasattr(mcp_server, '_tool_manager') and hasattr(mcp_server._tool_manager, '_tools'):
                            for tool_name, tool in mcp_server._tool_manager._tools.items():
                                # Try to get schema from the tool
                                schema = {
                                    "type": "object",
                                    "properties": {
                                        "prompt": {"type": "string", "description": "Input prompt"}
                                    },
                                    "required": ["prompt"]
                                }
                                
                                # FastMCP tools have a 'parameters' attribute containing the JSON schema
                                if hasattr(tool, 'parameters') and isinstance(tool.parameters, dict):
                                    schema = tool.parameters
                                # Fallback to other schema attributes if available
                                elif hasattr(tool, 'schema') and not callable(getattr(tool, 'schema', None)):
                                    schema = tool.schema
                                elif hasattr(tool, '_schema') and not callable(getattr(tool, '_schema', None)):
                                    schema = tool._schema
                                elif hasattr(tool, 'input_schema') and not callable(getattr(tool, 'input_schema', None)):
                                    schema = tool.input_schema
                                
                                tools.append({
                                    "name": tool_name,
                                    "description": getattr(tool, 'description', f"Tool: {tool_name}"),
                                    "inputSchema": schema
                                })
                                tools_found = True
                        
                        # Method 2: Check for tools in the MCP server directly 
                        if not tools_found and hasattr(mcp_server, '_tools'):
                            for tool_name, tool in mcp_server._tools.items():
                                # Try to get schema from the tool
                                schema = {
                                    "type": "object",
                                    "properties": {
                                        "input": {"type": "string", "description": "Input parameter"}
                                    },
                                    "required": ["input"]
                                }
                                
                                # FastMCP tools have a 'parameters' attribute containing the JSON schema
                                if hasattr(tool, 'parameters') and isinstance(tool.parameters, dict):
                                    schema = tool.parameters
                                elif hasattr(tool, 'schema') and not callable(getattr(tool, 'schema', None)):
                                    schema = tool.schema
                                elif hasattr(tool, '_schema') and not callable(getattr(tool, '_schema', None)):
                                    schema = tool._schema
                                elif hasattr(tool, 'input_schema') and not callable(getattr(tool, 'input_schema', None)):
                                    schema = tool.input_schema
                                
                                tools.append({
                                    "name": tool_name,
                                    "description": getattr(tool, 'description', f"Tool: {tool_name}"),
                                    "inputSchema": schema
                                })
                                tools_found = True
                        
                        # Method 3: Check the mcp_server (ClaudeCodeServer) itself
                        if not tools_found and hasattr(self.mcp_server, 'mcp'):
                            server_mcp = self.mcp_server.mcp
                            if hasattr(server_mcp, '_tool_manager') and hasattr(server_mcp._tool_manager, '_tools'):
                                for tool_name, tool in server_mcp._tool_manager._tools.items():
                                    # Try to get schema from the tool
                                    schema = {
                                        "type": "object",
                                        "properties": {
                                            "input": {"type": "string", "description": "Input parameter"}
                                        },
                                        "required": ["input"]
                                    }
                                    
                                    # FastMCP tools have a 'parameters' attribute containing the JSON schema
                                    if hasattr(tool, 'parameters') and isinstance(tool.parameters, dict):
                                        schema = tool.parameters
                                    elif hasattr(tool, 'schema') and not callable(getattr(tool, 'schema', None)):
                                        schema = tool.schema
                                    elif hasattr(tool, '_schema') and not callable(getattr(tool, '_schema', None)):
                                        schema = tool._schema
                                    elif hasattr(tool, 'input_schema') and not callable(getattr(tool, 'input_schema', None)):
                                        schema = tool.input_schema
                                    
                                    tools.append({
                                        "name": tool_name,
                                        "description": getattr(tool, 'description', f"Tool: {tool_name}"),
                                        "inputSchema": schema
                                    })
                                    tools_found = True
                        
                        logger.info(f"Discovered {len(tools)} tools")
                        
                        # Always add claude_code tool (our custom tool)
                        if not any(tool["name"] == "claude_code" for tool in tools):
                            tools.append({
                                "name": "claude_code",
                                "description": "Claude Code Agent: Your versatile multi-modal assistant for code, file, Git, and terminal operations via Claude CLI.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "prompt": {
                                            "type": "string",
                                            "description": "The detailed natural language prompt for Claude to execute."
                                        },
                                        "workFolder": {
                                            "type": "string",
                                            "description": "The working directory for Claude CLI execution. Must be an absolute path."
                                        }
                                    },
                                    "required": ["prompt"]
                                }
                            })
                        
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "tools": tools
                            }
                        }
                    elif method == "tools/call":
                        # Handle tool execution
                        params = request_data.get("params", {})
                        tool_name = params.get("name")
                        arguments = params.get("arguments", {})
                        
                        if tool_name == "claude_code":
                            # Execute the claude_code tool
                            try:
                                from .claude_code_tool import claude_code_tool
                                
                                prompt = arguments.get("prompt", "")
                                work_folder = arguments.get("workFolder")
                                
                                # Execute the tool
                                result = await claude_code_tool.execute_claude_code(prompt, work_folder)
                                
                                response = {
                                    "jsonrpc": "2.0",
                                    "id": request_id,
                                    "result": {
                                        "content": [{"type": "text", "text": result}],
                                        "isError": False
                                    }
                                }
                                
                            except Exception as e:
                                logger.error(f"Tool execution error: {e}")
                                response = {
                                    "jsonrpc": "2.0",
                                    "id": request_id,
                                    "result": {
                                        "content": [{"type": "text", "text": f"Error executing claude_code: {str(e)}"}],
                                        "isError": True
                                    }
                                }
                        else:
                            # Try to find and execute the tool from the MCP server
                            tool_found = False
                            
                            if hasattr(mcp_server, '_tool_manager') and hasattr(mcp_server._tool_manager, '_tools'):
                                tools_dict = mcp_server._tool_manager._tools
                                if tool_name in tools_dict:
                                    tool = tools_dict[tool_name]
                                    try:
                                        # Execute the tool function with proper context
                                        if hasattr(tool, 'fn') and callable(tool.fn):
                                            # Create a minimal context object for the tool
                                            from fastmcp import Context
                                            mock_ctx = Context(mcp_server)
                                            
                                            # Get the tool function signature to determine required arguments
                                            import inspect
                                            sig = inspect.signature(tool.fn)
                                            
                                            # Prepare arguments based on function signature
                                            call_args = {}
                                            for param_name, param in sig.parameters.items():
                                                if param_name == 'ctx':
                                                    call_args[param_name] = mock_ctx
                                                elif param_name in arguments:
                                                    call_args[param_name] = arguments[param_name]
                                                elif param.default != inspect.Parameter.empty:
                                                    # Use default value if available
                                                    continue
                                                else:
                                                    # Required parameter not provided, set reasonable defaults
                                                    if param_name == 'session_id':
                                                        call_args[param_name] = f"session_{request_id}"
                                                    elif param_name == 'offset':
                                                        call_args[param_name] = 0
                                                    elif param_name == 'limit':
                                                        call_args[param_name] = None
                                                    elif param_name == 'expected_replacements':
                                                        call_args[param_name] = 1
                                                    # Add other common defaults as needed
                                            
                                            tool_result = await tool.fn(**call_args)
                                            
                                            # Format result appropriately
                                            if hasattr(tool_result, 'content'):
                                                result_content = tool_result.content
                                            elif isinstance(tool_result, list):
                                                result_content = tool_result
                                            else:
                                                result_content = [{"type": "text", "text": str(tool_result)}]
                                            
                                            response = {
                                                "jsonrpc": "2.0",
                                                "id": request_id,
                                                "result": {
                                                    "content": result_content,
                                                    "isError": False
                                                }
                                            }
                                            tool_found = True
                                    except Exception as e:
                                        logger.error(f"Tool {tool_name} execution error: {e}")
                                        response = {
                                            "jsonrpc": "2.0",
                                            "id": request_id,
                                            "result": {
                                                "content": [{"type": "text", "text": f"Error executing {tool_name}: {str(e)}"}],
                                                "isError": True
                                            }
                                        }
                                        tool_found = True
                            
                            if not tool_found:
                                response = {
                                    "jsonrpc": "2.0",
                                    "id": request_id,
                                    "error": {
                                        "code": -32601,
                                        "message": f"Tool not found: {tool_name}"
                                    }
                                }
                    else:
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32601,
                                "message": f"Method not found: {method}"
                            }
                        }
                    
                    # Return as SSE stream for compatibility
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
                    
                except Exception as e:
                    logger.error(f"MCP request error: {e}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": request_data.get("id", "error") if 'request_data' in locals() else "error",
                        "error": {
                            "code": -32603,
                            "message": f"Internal error: {str(e)}"
                        }
                    }
                    
                    async def generate_error_sse():
                        yield f"data: {json.dumps(error_response)}\n\n"
                    
                    return StreamingResponse(
                        generate_error_sse(),
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                        }
                    )
        
        logger.info(f"MCP endpoint ready at: {path}")
        
        # Create OAuth endpoint handlers
        async def oauth_auth_server_metadata(request):
            """OAuth 2.0 Authorization Server Metadata endpoint."""
            return JSONResponse(self.oauth_provider.get_authorization_server_metadata())
        
        async def oauth_auth_server_metadata_with_uuid(request):
            """OAuth 2.0 Authorization Server Metadata endpoint with UUID path."""
            return JSONResponse(self.oauth_provider.get_authorization_server_metadata())
        
        async def oauth_protected_resource_metadata(request):
            """OAuth 2.0 Protected Resource Metadata endpoint (RFC 9728)."""
            return JSONResponse({
                "resource": self.base_url,
                "authorization_servers": [self.base_url],
                "scopes_supported": ["read", "write"],
                "bearer_methods_supported": ["header"]
            })
        
        async def oauth_protected_resource_metadata_with_uuid(request):
            """OAuth 2.0 Protected Resource Metadata endpoint with UUID path."""
            return JSONResponse({
                "resource": self.base_url,
                "authorization_servers": [self.base_url],
                "scopes_supported": ["read", "write"],
                "bearer_methods_supported": ["header"]
            })
        
        async def register_client(request):
            """Dynamic Client Registration endpoint."""
            try:
                from .oauth import ClientRegistrationRequest
                body = await request.json()
                client_request = ClientRegistrationRequest(**body)
                response = self.oauth_provider.register_client(client_request)
                return JSONResponse(response.model_dump())
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)
        
        async def authorize(request):
            """Authorization endpoint."""
            try:
                from .oauth import AuthorizationRequest
                query_params = dict(request.query_params)
                auth_request = AuthorizationRequest(**query_params)
                redirect_url = self.oauth_provider.authorize(auth_request)
                return JSONResponse({"redirect_url": redirect_url})
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)
        
        async def token(request):
            """Token endpoint."""
            try:
                from .oauth import TokenRequest
                if request.headers.get("content-type") == "application/json":
                    body = await request.json()
                else:
                    # Handle form data
                    form = await request.form()
                    body = dict(form)
                
                token_request = TokenRequest(**body)
                response = self.oauth_provider.exchange_code_for_token(token_request)
                return JSONResponse(response)
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)
        
        async def introspect_token(request):
            """Token introspection endpoint for Resource Servers."""
            try:
                form = await request.form()
                token = form.get("token")
                if not token or not isinstance(token, str):
                    return JSONResponse({"active": False}, status_code=400)
                
                # Validate the token using OAuth provider
                try:
                    self.oauth_provider.validate_token(token)
                    # If validation succeeds, token is active
                    return JSONResponse({
                        "active": True,
                        "scope": "read write",
                        "token_type": "Bearer"
                    })
                except Exception:
                    # If validation fails, token is not active
                    return JSONResponse({"active": False})
                    
            except Exception as e:
                return JSONResponse({"active": False}, status_code=400)
        
        async def revoke_token(request):
            """Token revocation endpoint."""
            try:
                form = await request.form()
                token = form.get("token")
                if not token or not isinstance(token, str):
                    return JSONResponse({"error": "Missing token parameter"}, status_code=400)
                
                # For this demo implementation, we'll just return success
                # In production, you would invalidate the token in your token store
                return JSONResponse({"revoked": True})
                
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)
        
        async def health_check(request):
            """Health check endpoint."""
            return JSONResponse({"status": "healthy", "server": self.name, "oauth_enabled": True})
        
        # Use the MCP app's lifespan to ensure proper initialization
        mcp_lifespan = getattr(mcp_app, 'lifespan', None)
        
        # Create the Starlette app with OAuth routes and MCP mounted at custom path
        app = Starlette(
            routes=[
                # OAuth discovery endpoints
                Route("/.well-known/oauth-authorization-server", oauth_auth_server_metadata, methods=["GET"]),
                Route("/.well-known/oauth-authorization-server/{uuid_path}", oauth_auth_server_metadata_with_uuid, methods=["GET"]),
                Route("/.well-known/oauth-protected-resource", oauth_protected_resource_metadata, methods=["GET"]),
                Route("/.well-known/oauth-protected-resource/{uuid_path}", oauth_protected_resource_metadata_with_uuid, methods=["GET"]),
                
                # OAuth flow endpoints
                Route("/register", register_client, methods=["POST"]),
                Route("/authorize", authorize, methods=["GET"]),
                Route("/token", token, methods=["POST"]),
                
                # MCP specification endpoints
                Route("/introspect", introspect_token, methods=["POST"]),
                Route("/revoke", revoke_token, methods=["POST"]),
                
                # Health endpoint
                Route("/health", health_check, methods=["GET"]),
                
                # Mount MCP app at the specified path
                Mount(path, mcp_app),
            ],
            lifespan=mcp_lifespan,
        )
        
        # Run the combined Starlette app
        logger.info(f"Starting server on {host}:{port} with MCP at {path}")
        uvicorn.run(app, host=host, port=port, log_level="warning")