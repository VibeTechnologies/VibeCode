"""Comprehensive integration tests for vibecode package - covering all endpoints."""

import subprocess
import sys
import time
import pytest
from pathlib import Path
import threading
import requests
import uuid
import json
from contextlib import contextmanager


def test_vibecode_cli_help():
    """Test that vibecode CLI is available and shows help."""
    result = subprocess.run([sys.executable, "-m", "vibecode.cli", "--help"], 
                          capture_output=True, text=True)
    assert result.returncode == 0
    assert "vibecode" in result.stdout
    assert "Start MCP server" in result.stdout


def test_vibecode_start_help():
    """Test that vibecode start command shows help."""
    result = subprocess.run([sys.executable, "-m", "vibecode.cli", "start", "--help"], 
                          capture_output=True, text=True)
    assert result.returncode == 0
    assert "--port" in result.stdout
    assert "--no-tunnel" in result.stdout


def test_vibecode_local_mode():
    """Test that vibecode starts in local mode without tunnel."""
    # Start vibecode in local mode
    proc = subprocess.Popen([
        sys.executable, "-m", "vibecode.cli", "start", 
        "--no-tunnel", "--port", "8334"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    try:
        # Wait a few seconds for startup
        time.sleep(3)
        
        # Check if process is still running
        assert proc.poll() is None, "vibecode process should still be running"
        
        # Test passed if we get here
        print("✅ Local mode test passed")
        
    finally:
        # Clean up
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_package_structure():
    """Test that package has required structure."""
    pkg_root = Path(__file__).parent.parent
    
    # Check required files exist
    assert (pkg_root / "vibecode" / "__init__.py").exists()
    assert (pkg_root / "vibecode" / "cli.py").exists()
    assert (pkg_root / "pyproject.toml").exists()
    assert (pkg_root / "README.md").exists()
    assert (pkg_root / "LICENSE").exists()


@contextmanager
def run_test_server(port):
    """Context manager to run test server and clean up properly."""
    try:
        from vibecode.server import AuthenticatedMCPServer
        import threading
        import time
        import uuid
        
        # Create server instance
        server = AuthenticatedMCPServer(base_url=f"http://localhost:{port}")
        
        # Generate a unique UUID for this test
        test_uuid = str(uuid.uuid4()).replace('-', '')
        
        server_exception = None
        
        def run_server():
            nonlocal server_exception
            try:
                # Start the server - this should work without errors
                server.run_sse_with_auth(host="127.0.0.1", port=port, path=f"/{test_uuid}")
            except Exception as e:
                server_exception = e
        
        # Start server in background thread
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        # Wait for server to start
        time.sleep(2)
        
        # Check if server started successfully
        if server_exception:
            raise server_exception
        
        yield f"http://127.0.0.1:{port}", test_uuid
        
    except ImportError:
        pytest.skip("mcp-claude-code not available")


def test_comprehensive_oauth_endpoints():
    """Test all OAuth 2.1 endpoints comprehensively."""
    with run_test_server(8340) as (base_url, test_uuid):
        
        print(f"🧪 Testing OAuth endpoints on {base_url} with UUID: {test_uuid}")
        
        # ==================== OAuth Discovery Endpoints ====================
        
        # Test 1: OAuth Authorization Server Metadata (base)
        response = requests.get(f"{base_url}/.well-known/oauth-authorization-server")
        assert response.status_code == 200, f"OAuth auth server metadata failed: {response.status_code}"
        metadata = response.json()
        assert "issuer" in metadata
        assert "authorization_endpoint" in metadata
        assert "token_endpoint" in metadata
        assert "registration_endpoint" in metadata
        print("✅ OAuth Authorization Server Metadata (base) - 200 OK")
        
        # Test 2: OAuth Authorization Server Metadata (with UUID - Claude.ai bug workaround)
        response = requests.get(f"{base_url}/.well-known/oauth-authorization-server/{test_uuid}")
        assert response.status_code == 200, f"OAuth auth server metadata with UUID failed: {response.status_code}"
        metadata_uuid = response.json()
        assert metadata == metadata_uuid, "UUID version should return same metadata"
        print("✅ OAuth Authorization Server Metadata (with UUID) - 200 OK")
        
        # Test 3: OAuth Protected Resource Metadata (base)
        response = requests.get(f"{base_url}/.well-known/oauth-protected-resource")
        assert response.status_code == 200, f"OAuth protected resource metadata failed: {response.status_code}"
        resource_metadata = response.json()
        assert "resource" in resource_metadata
        assert "authorization_servers" in resource_metadata
        assert "scopes_supported" in resource_metadata
        print("✅ OAuth Protected Resource Metadata (base) - 200 OK")
        
        # Test 4: OAuth Protected Resource Metadata (with UUID - Claude.ai bug workaround)
        response = requests.get(f"{base_url}/.well-known/oauth-protected-resource/{test_uuid}")
        assert response.status_code == 200, f"OAuth protected resource metadata with UUID failed: {response.status_code}"
        resource_metadata_uuid = response.json()
        assert resource_metadata == resource_metadata_uuid, "UUID version should return same metadata"
        print("✅ OAuth Protected Resource Metadata (with UUID) - 200 OK")
        
        # ==================== OAuth Flow Endpoints ====================
        
        # Test 5: Dynamic Client Registration
        registration_data = {
            "redirect_uris": ["https://example.com/callback", "http://localhost:3000/callback"],
            "client_name": "Test Client",
            "client_uri": "https://example.com",
            "scope": "read write",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none"
        }
        response = requests.post(f"{base_url}/register", json=registration_data)
        assert response.status_code == 200, f"Client registration failed: {response.status_code}"
        client_data = response.json()
        assert "client_id" in client_data
        assert client_data["client_secret"] is None  # Public client
        client_id = client_data["client_id"]
        print("✅ Dynamic Client Registration - 200 OK")
        
        # Test 6: Authorization Endpoint
        auth_params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://example.com/callback",
            "scope": "read write",
            "state": "test_state",
            "code_challenge": "test_challenge",
            "code_challenge_method": "S256"
        }
        response = requests.get(f"{base_url}/authorize", params=auth_params)
        assert response.status_code == 200, f"Authorization endpoint failed: {response.status_code}"
        auth_response = response.json()
        assert "redirect_url" in auth_response
        print("✅ Authorization Endpoint - 200 OK")
        
        # Test 7: Token Endpoint (JSON format)
        token_data = {
            "grant_type": "authorization_code",
            "code": "test_auth_code",
            "redirect_uri": "https://example.com/callback",
            "client_id": client_id,
            "code_verifier": "test_verifier"
        }
        response = requests.post(f"{base_url}/token", json=token_data, headers={
            "Content-Type": "application/json"
        })
        # This should fail with invalid code, but shouldn't crash
        assert response.status_code in [200, 400], f"Token endpoint JSON failed: {response.status_code}"
        print("✅ Token Endpoint (JSON) - handled correctly")
        
        # Test 8: Token Endpoint (Form data format)
        response = requests.post(f"{base_url}/token", data=token_data)
        # This should fail with invalid code, but shouldn't crash
        assert response.status_code in [200, 400], f"Token endpoint form failed: {response.status_code}"
        print("✅ Token Endpoint (Form) - handled correctly")
        
        # ==================== MCP Specification Endpoints ====================
        
        # Test 9: Token Introspection (RFC 7662)
        response = requests.post(f"{base_url}/introspect", data={"token": "test_token"})
        assert response.status_code == 200, f"Introspection endpoint failed: {response.status_code}"
        introspect_data = response.json()
        assert "active" in introspect_data
        # Should be false for invalid token
        assert introspect_data["active"] is False
        print("✅ Token Introspection Endpoint - 200 OK")
        
        # Test 10: Token Revocation (RFC 7009)
        response = requests.post(f"{base_url}/revoke", data={"token": "test_token"})
        assert response.status_code == 200, f"Revocation endpoint failed: {response.status_code}"
        revoke_data = response.json()
        assert "revoked" in revoke_data
        print("✅ Token Revocation Endpoint - 200 OK")
        
        # Test 11: Health Check
        response = requests.get(f"{base_url}/health")
        assert response.status_code == 200, f"Health endpoint failed: {response.status_code}"
        health_data = response.json()
        assert health_data["status"] == "healthy"
        assert health_data["oauth_enabled"] is True
        print("✅ Health Check Endpoint - 200 OK")
        
        print("🎉 All OAuth endpoints tested successfully!")


def test_mcp_endpoint_functionality():
    """Test MCP endpoint functionality and proper SSE headers."""
    with run_test_server(8341) as (base_url, test_uuid):
        
        print(f"🧪 Testing MCP endpoint functionality on {base_url}")
        
        # Test MCP endpoint with proper headers (MCP is mounted at the UUID path)
        mcp_response = requests.post(
            f"{base_url}/{test_uuid}",
            timeout=10,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}}
        )
        
        print(f"MCP endpoint response status: {mcp_response.status_code}")
        print(f"MCP endpoint response headers: {dict(mcp_response.headers)}")
        
        # Should get 200 OK with proper SSE response
        assert mcp_response.status_code == 200, f"MCP endpoint failed: {mcp_response.status_code}"
        
        # Check for SSE headers
        headers = mcp_response.headers
        assert "text/event-stream" in headers.get("content-type", ""), "Should have SSE content-type"
        
        # Should have MCP session ID if using real MCP server
        if "mcp-session-id" in headers:
            print("✅ MCP session ID header present")
        
        print("✅ MCP Endpoint - 200 OK with proper SSE headers")
        
        # Test MCP endpoint with valid initialized request (no specific method needed)
        mcp_response2 = requests.post(
            f"{base_url}/{test_uuid}",
            timeout=10,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={"jsonrpc": "2.0", "method": "initialize", "id": 2, "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}
        )
        
        assert mcp_response2.status_code == 200, f"MCP second request failed: {mcp_response2.status_code}"
        print("✅ MCP Second Request - 200 OK")


def test_error_handling_and_edge_cases():
    """Test error handling for all endpoints."""
    with run_test_server(8342) as (base_url, test_uuid):
        
        print(f"🧪 Testing error handling and edge cases on {base_url}")
        
        # Test 1: Invalid JSON in client registration
        response = requests.post(f"{base_url}/register", json={"invalid": "data"})
        assert response.status_code == 400, f"Should reject invalid registration data"
        print("✅ Invalid client registration data - 400 error")
        
        # Test 2: Missing parameters in authorization
        response = requests.get(f"{base_url}/authorize")
        assert response.status_code == 400, f"Should reject missing auth parameters"
        print("✅ Missing authorization parameters - 400 error")
        
        # Test 3: Empty token in introspection
        response = requests.post(f"{base_url}/introspect", data={})
        assert response.status_code == 400, f"Should reject empty introspection"
        print("✅ Empty token introspection - 400 error")
        
        # Test 4: Empty token in revocation
        response = requests.post(f"{base_url}/revoke", data={})
        assert response.status_code == 400, f"Should reject empty revocation"
        print("✅ Empty token revocation - 400 error")
        
        # Test 5: Invalid HTTP method on OAuth endpoints
        response = requests.post(f"{base_url}/.well-known/oauth-authorization-server")
        assert response.status_code in [405, 404], f"Should reject POST on GET-only endpoint"
        print("✅ Invalid HTTP method - handled correctly")
        
        # Test 6: Malformed JSON in MCP request
        response = requests.post(
            f"{base_url}/{test_uuid}",
            headers={"Content-Type": "application/json"},
            data="invalid json"
        )
        # Should handle gracefully (may return various error codes depending on implementation)
        assert response.status_code in [400, 406, 422, 500], f"Should handle malformed JSON gracefully, got {response.status_code}"
        print("✅ Malformed JSON in MCP request - handled gracefully")


def test_uuid_path_compatibility():
    """Test Claude.ai UUID path compatibility specifically."""
    with run_test_server(8343) as (base_url, test_uuid):
        
        print(f"🧪 Testing Claude.ai UUID path compatibility with UUID: {test_uuid}")
        
        # Test all OAuth discovery endpoints with UUID paths (Claude.ai bug)
        uuid_endpoints = [
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-protected-resource"
        ]
        
        for endpoint in uuid_endpoints:
            # Test base endpoint
            response_base = requests.get(f"{base_url}{endpoint}")
            assert response_base.status_code == 200, f"Base {endpoint} failed"
            base_data = response_base.json()
            
            # Test UUID endpoint (Claude.ai incorrectly appends UUID)
            response_uuid = requests.get(f"{base_url}{endpoint}/{test_uuid}")
            assert response_uuid.status_code == 200, f"UUID {endpoint} failed"
            uuid_data = response_uuid.json()
            
            # Both should return identical data
            assert base_data == uuid_data, f"UUID version of {endpoint} should match base"
            print(f"✅ {endpoint} - both base and UUID versions work")
        
        # Test random UUID paths (should also work due to {uuid_path} wildcard)
        random_uuid = str(uuid.uuid4())
        response = requests.get(f"{base_url}/.well-known/oauth-authorization-server/{random_uuid}")
        assert response.status_code == 200, f"Random UUID path should work"
        print("✅ Random UUID paths handled correctly")


def test_concurrent_requests():
    """Test handling multiple concurrent requests."""
    with run_test_server(8344) as (base_url, test_uuid):
        
        print(f"🧪 Testing concurrent request handling on {base_url}")
        
        import threading
        import time
        
        results = []
        errors = []
        
        def make_request(endpoint, method="GET", data=None):
            try:
                if method == "GET":
                    response = requests.get(f"{base_url}{endpoint}", timeout=5)
                else:
                    response = requests.post(f"{base_url}{endpoint}", json=data, timeout=5)
                results.append((endpoint, response.status_code))
            except Exception as e:
                errors.append((endpoint, str(e)))
        
        # Create multiple concurrent requests
        threads = []
        endpoints_to_test = [
            ("/.well-known/oauth-authorization-server", "GET", None),
            ("/.well-known/oauth-protected-resource", "GET", None),
            ("/health", "GET", None),
            ("/introspect", "POST", None),  # Will fail but shouldn't crash
            ("/revoke", "POST", None),      # Will fail but shouldn't crash
        ]
        
        # Launch concurrent requests
        for endpoint, method, data in endpoints_to_test:
            thread = threading.Thread(target=make_request, args=(endpoint, method, data))
            threads.append(thread)
            thread.start()
        
        # Wait for all requests to complete
        for thread in threads:
            thread.join(timeout=10)
        
        # Check results
        assert len(errors) == 0, f"Concurrent requests had errors: {errors}"
        assert len(results) == len(endpoints_to_test), f"Not all requests completed"
        
        # All discovery endpoints should return 200
        discovery_results = [(e, s) for e, s in results if "well-known" in e or e == "/health"]
        assert all(status == 200 for _, status in discovery_results), "Discovery endpoints should all return 200"
        
        print("✅ Concurrent requests handled successfully")


def test_original_bugfix_verification():
    """Verify the original TypeError bug is completely fixed."""
    with run_test_server(8345) as (base_url, test_uuid):
        
        print(f"🧪 Verifying original TypeError bug fix on {base_url}")
        
        # This is the exact request that originally caused:
        # TypeError: argument of type 'function' is not iterable
        response = requests.post(
            f"{base_url}/{test_uuid}",
            timeout=5,
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1}
        )
        
        # Should NOT get 500 Internal Server Error anymore (the original TypeError bug)
        assert response.status_code != 500, "Original TypeError should be fixed - no 500 errors"
        # May get 200 (success) or 406 (content negotiation issue) but NOT 500 (server error)
        assert response.status_code in [200, 406], f"Should get 200 or 406, not 500, got {response.status_code}"
        
        print("✅ Original TypeError bug is COMPLETELY FIXED")
        print(f"   Status: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")


def test_mcp_architecture_validation():
    """Validate the new MCP-as-main-app architecture works correctly."""
    with run_test_server(8346) as (base_url, test_uuid):
        
        print(f"🧪 Validating MCP architecture on {base_url}")
        
        # Test 1: MCP endpoint is available at the UUID path
        response = requests.post(
            f"{base_url}/{test_uuid}",
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            },
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}}
        )
        # Should be accessible (200 success or 406 content negotiation, but not 404)
        assert response.status_code in [200, 406], f"MCP endpoint should be available, got {response.status_code}"
        
        # Test 2: OAuth endpoints are available via custom routes
        oauth_endpoints = [
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-protected-resource",
            "/health"
        ]
        
        for endpoint in oauth_endpoints:
            response = requests.get(f"{base_url}{endpoint}")
            assert response.status_code == 200, f"OAuth endpoint {endpoint} should be available"
        
        # Test 3: Both systems work together (MCP + OAuth)
        # Make OAuth discovery request
        oauth_response = requests.get(f"{base_url}/.well-known/oauth-authorization-server")
        assert oauth_response.status_code == 200
        
        # Make MCP request immediately after
        mcp_response = requests.post(
            f"{base_url}/{test_uuid}",
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "method": "initialize", "id": 2, "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}
        )
        assert mcp_response.status_code in [200, 406], f"MCP should work, got {mcp_response.status_code}"
        
        print("✅ New MCP architecture validation passed")
        print("   - MCP server is main app ✓")
        print("   - OAuth endpoints via custom_route ✓") 
        print("   - Both systems work together ✓")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])