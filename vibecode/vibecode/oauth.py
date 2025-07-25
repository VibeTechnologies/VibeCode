"""OAuth 2.1 implementation for MCP server with Dynamic Client Registration support."""

import json
import secrets
import time
import uuid
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request, Depends, Form, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, HttpUrl
import httpx
from jose import jwt, JWTError


class ClientRegistrationRequest(BaseModel):
    """OAuth 2.0 Dynamic Client Registration request."""
    redirect_uris: List[HttpUrl]
    client_name: Optional[str] = None
    client_uri: Optional[HttpUrl] = None
    logo_uri: Optional[HttpUrl] = None
    scope: Optional[str] = None
    contacts: Optional[List[str]] = None
    tos_uri: Optional[HttpUrl] = None
    policy_uri: Optional[HttpUrl] = None
    token_endpoint_auth_method: Optional[str] = "none"  # For public clients (PKCE)
    grant_types: Optional[List[str]] = ["authorization_code"]
    response_types: Optional[List[str]] = ["code"]


class ClientRegistrationResponse(BaseModel):
    """OAuth 2.0 Dynamic Client Registration response."""
    client_id: str
    client_secret: Optional[str] = None  # None for public clients
    redirect_uris: List[str]
    client_name: Optional[str] = None
    client_uri: Optional[str] = None
    logo_uri: Optional[str] = None
    scope: str
    contacts: Optional[List[str]] = None
    tos_uri: Optional[str] = None
    policy_uri: Optional[str] = None
    token_endpoint_auth_method: str
    grant_types: List[str]
    response_types: List[str]
    registration_access_token: Optional[str] = None
    registration_client_uri: Optional[str] = None
    client_id_issued_at: int
    client_secret_expires_at: int = 0  # 0 means never expires


class AuthorizationRequest(BaseModel):
    """OAuth 2.0 Authorization request parameters."""
    response_type: str
    client_id: str
    redirect_uri: HttpUrl
    scope: Optional[str] = None
    state: Optional[str] = None
    code_challenge: Optional[str] = None  # PKCE
    code_challenge_method: Optional[str] = None  # PKCE


class TokenRequest(BaseModel):
    """OAuth 2.0 Token request parameters."""
    grant_type: str
    code: Optional[str] = None
    redirect_uri: Optional[HttpUrl] = None
    client_id: Optional[str] = None
    code_verifier: Optional[str] = None  # PKCE


class OAuthProvider:
    """OAuth 2.1 provider with Dynamic Client Registration for MCP servers."""
    
    def __init__(self, base_url: str, jwt_secret: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.jwt_secret = jwt_secret or secrets.token_urlsafe(32)
        
        # In-memory storage (for production, use persistent storage)
        self.clients: Dict[str, Dict[str, Any]] = {}
        self.authorization_codes: Dict[str, Dict[str, Any]] = {}
        self.access_tokens: Dict[str, Dict[str, Any]] = {}
        
        # Default scopes
        self.supported_scopes = ["read", "write", "admin"]
        
    def _generate_client_id(self) -> str:
        """Generate a unique client ID."""
        return f"mcp_client_{uuid.uuid4().hex[:16]}"
    
    def _generate_client_secret(self) -> str:
        """Generate a client secret."""
        return secrets.token_urlsafe(32)
    
    def _generate_authorization_code(self) -> str:
        """Generate an authorization code."""
        return secrets.token_urlsafe(32)
    
    def _generate_access_token(self, client_id: str, scope: str) -> str:
        """Generate a JWT access token."""
        payload = {
            "iss": self.base_url,
            "sub": client_id,
            "aud": f"{self.base_url}/mcp",
            "exp": int(time.time()) + 3600,  # 1 hour
            "iat": int(time.time()),
            "scope": scope,
            "client_id": client_id
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def register_client(self, request: ClientRegistrationRequest) -> ClientRegistrationResponse:
        """Register a new OAuth client (Dynamic Client Registration)."""
        client_id = self._generate_client_id()
        client_secret = None  # Public client for PKCE
        
        # Validate redirect URIs (must be localhost or HTTPS)
        for uri in request.redirect_uris:
            if not (uri.scheme == "https" or uri.host in ["localhost", "127.0.0.1"]):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid redirect URI: must be localhost or HTTPS"
                )
        
        # Store client
        client_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [str(uri) for uri in request.redirect_uris],
            "client_name": request.client_name,
            "client_uri": str(request.client_uri) if request.client_uri else None,
            "logo_uri": str(request.logo_uri) if request.logo_uri else None,
            "scope": request.scope or "read",
            "contacts": request.contacts,
            "tos_uri": str(request.tos_uri) if request.tos_uri else None,
            "policy_uri": str(request.policy_uri) if request.policy_uri else None,
            "token_endpoint_auth_method": request.token_endpoint_auth_method,
            "grant_types": request.grant_types,
            "response_types": request.response_types,
            "client_id_issued_at": int(time.time()),
        }
        
        self.clients[client_id] = client_data
        
        return ClientRegistrationResponse(**client_data)
    
    def authorize(self, request: AuthorizationRequest) -> str:
        """Handle authorization request (Authorization Code Grant with PKCE)."""
        # Validate client
        if request.client_id not in self.clients:
            raise HTTPException(status_code=400, detail="Invalid client_id")
        
        client = self.clients[request.client_id]
        
        # Validate redirect URI
        if str(request.redirect_uri) not in client["redirect_uris"]:
            raise HTTPException(status_code=400, detail="Invalid redirect_uri")
        
        # Validate response type
        if request.response_type != "code":
            raise HTTPException(status_code=400, detail="Unsupported response_type")
        
        # Validate PKCE parameters
        if not request.code_challenge:
            raise HTTPException(status_code=400, detail="code_challenge required")
        
        if request.code_challenge_method not in ["S256", "plain"]:
            raise HTTPException(status_code=400, detail="Invalid code_challenge_method")
        
        # Generate authorization code
        auth_code = self._generate_authorization_code()
        
        # Store authorization code with PKCE data
        self.authorization_codes[auth_code] = {
            "client_id": request.client_id,
            "redirect_uri": str(request.redirect_uri),
            "scope": request.scope or client["scope"],
            "state": request.state,
            "code_challenge": request.code_challenge,
            "code_challenge_method": request.code_challenge_method,
            "expires_at": time.time() + 600,  # 10 minutes
        }
        
        # Build redirect URL with authorization code
        redirect_url = f"{request.redirect_uri}?code={auth_code}"
        if request.state:
            redirect_url += f"&state={request.state}"
        
        return redirect_url
    
    def exchange_code_for_token(self, request: TokenRequest) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        if request.grant_type != "authorization_code":
            raise HTTPException(status_code=400, detail="Unsupported grant_type")
        
        if not request.code:
            raise HTTPException(status_code=400, detail="Missing authorization code")
        
        # Validate authorization code
        if request.code not in self.authorization_codes:
            raise HTTPException(status_code=400, detail="Invalid authorization code")
        
        auth_data = self.authorization_codes[request.code]
        
        # Check expiration
        if time.time() > auth_data["expires_at"]:
            del self.authorization_codes[request.code]
            raise HTTPException(status_code=400, detail="Authorization code expired")
        
        # Validate client
        if request.client_id != auth_data["client_id"]:
            raise HTTPException(status_code=400, detail="Invalid client_id")
        
        # Validate redirect URI
        if str(request.redirect_uri) != auth_data["redirect_uri"]:
            raise HTTPException(status_code=400, detail="Invalid redirect_uri")
        
        # Validate PKCE code verifier
        if not request.code_verifier:
            raise HTTPException(status_code=400, detail="Missing code_verifier")
        
        # TODO: Implement proper PKCE validation (S256 hash check)
        
        # Generate access token
        access_token = self._generate_access_token(
            auth_data["client_id"], 
            auth_data["scope"]
        )
        
        # Store access token
        self.access_tokens[access_token] = {
            "client_id": auth_data["client_id"],
            "scope": auth_data["scope"],
            "expires_at": time.time() + 3600,  # 1 hour
        }
        
        # Clean up authorization code
        del self.authorization_codes[request.code]
        
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": auth_data["scope"]
        }
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate an access token."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            
            # Check if token exists in our store
            if token not in self.access_tokens:
                raise HTTPException(status_code=401, detail="Invalid token")
            
            token_data = self.access_tokens[token]
            
            # Check expiration
            if time.time() > token_data["expires_at"]:
                del self.access_tokens[token]
                raise HTTPException(status_code=401, detail="Token expired")
            
            return {
                "client_id": payload["client_id"],
                "scope": payload["scope"],
                "valid": True
            }
            
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")
    
    def get_authorization_server_metadata(self) -> Dict[str, Any]:
        """Return OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
        return {
            "issuer": self.base_url,
            "authorization_endpoint": f"{self.base_url}/authorize",
            "token_endpoint": f"{self.base_url}/token",
            "registration_endpoint": f"{self.base_url}/register",
            "scopes_supported": self.supported_scopes,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "token_endpoint_auth_methods_supported": ["none"],  # PKCE
            "code_challenge_methods_supported": ["S256", "plain"],
            "registration_endpoint_auth_methods_supported": ["none"],
        }


def create_oauth_app(oauth_provider: OAuthProvider, path_prefix: str = "") -> FastAPI:
    """Create FastAPI app with OAuth endpoints."""
    app = FastAPI(title="MCP OAuth Provider", docs_url=None, redoc_url=None)
    
    security = HTTPBearer(auto_error=False)
    
    @app.get(f"{path_prefix}/.well-known/oauth-authorization-server")
    async def get_authorization_server_metadata():
        """OAuth 2.0 Authorization Server Metadata endpoint."""
        return oauth_provider.get_authorization_server_metadata()
    
    @app.post(f"{path_prefix}/register")
    async def register_client(request: ClientRegistrationRequest):
        """Dynamic Client Registration endpoint."""
        try:
            response = oauth_provider.register_client(request)
            return response.model_dump()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get(f"{path_prefix}/authorize")
    async def authorize(
        response_type: str = Query(...),
        client_id: str = Query(...),
        redirect_uri: str = Query(...),
        scope: Optional[str] = Query(None),
        state: Optional[str] = Query(None),
        code_challenge: Optional[str] = Query(None),
        code_challenge_method: Optional[str] = Query(None)
    ):
        """Authorization endpoint."""
        try:
            auth_request = AuthorizationRequest(
                response_type=response_type,
                client_id=client_id,
                redirect_uri=redirect_uri,
                scope=scope,
                state=state,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method
            )
            redirect_url = oauth_provider.authorize(auth_request)
            return RedirectResponse(url=redirect_url)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.post(f"{path_prefix}/token")
    async def token(
        grant_type: str = Form(...),
        code: Optional[str] = Form(None),
        redirect_uri: Optional[str] = Form(None),
        client_id: Optional[str] = Form(None),
        code_verifier: Optional[str] = Form(None)
    ):
        """Token endpoint."""
        try:
            token_request = TokenRequest(
                grant_type=grant_type,
                code=code,
                redirect_uri=redirect_uri,
                client_id=client_id,
                code_verifier=code_verifier
            )
            response = oauth_provider.exchange_code_for_token(token_request)
            return response
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Dependency to get current authenticated user."""
        if not credentials:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        try:
            token_data = oauth_provider.validate_token(credentials.credentials)
            return token_data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=401, detail="Invalid token")
    
    return app, get_current_user