"""Combined OAuth and MCP server implementation."""

import asyncio
from typing import Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .oauth import OAuthProvider, create_oauth_app

try:
    from mcp_claude_code.server import ClaudeCodeServer
except ImportError:
    # Use mock for testing when mcp-claude-code is not available
    from .mock_mcp import MockClaudeCodeServer as ClaudeCodeServer


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
        
        # Create combined FastAPI app
        self.app = None
    
    def run_sse_with_auth(
        self,
        host: str = "0.0.0.0",
        port: int = 8300,
        path: str = "/mcp"
    ):
        """Run MCP server with OAuth 2.1 authentication using Starlette with proper path mounting."""
        
        import contextlib
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        from starlette.responses import JSONResponse
        import uvicorn
        
        # Get the MCP server's HTTP app and extract the actual handler
        mcp_server = self.mcp_server.mcp
        mcp_app = mcp_server.http_app()
        
        # Extract the actual MCP handler from the internal mount
        mcp_handler = None
        for route in mcp_app.routes:
            if hasattr(route, 'path') and route.path == '/mcp':
                mcp_handler = route.app
                break
        
        if not mcp_handler:
            raise RuntimeError("Could not find MCP handler in the FastMCP app")
        
        print(f"🚀 Using Starlette with MCP handler mounted at custom path")
        print(f"🚀 MCP server type: {type(mcp_server)}")
        print(f"🚀 MCP will be available at: {path}")
        print(f"🚀 MCP handler type: {type(mcp_handler)}")
        
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
        mcp_lifespan = mcp_app.lifespan if hasattr(mcp_app, 'lifespan') else None
        
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
                
                # Mount MCP handler at the specified path
                Mount(path, mcp_handler),
            ],
            lifespan=mcp_lifespan,
        )
        
        # Run the combined Starlette app
        print(f"🚀 Starting combined server (OAuth + MCP) on {host}:{port}")
        print(f"🚀 MCP mounted at: {path}")
        print(f"🚀 OAuth endpoints available at root level")
        uvicorn.run(app, host=host, port=port)