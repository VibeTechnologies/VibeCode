# Suppress all warnings before any imports
import warnings
import os
warnings.simplefilter("ignore")
os.environ["PYDANTIC_DISABLE_WARNINGS"] = "1"

# Apply compatibility patches before other imports
try:
    from .compatibility_patch import patch_mcp_imports
    patch_mcp_imports()
except ImportError:
    # If compatibility patch is not available, try a direct fix
    try:
        import mcp
        import mcp.types
        if not hasattr(mcp, 'McpError'):
            mcp.McpError = mcp.types.JSONRPCError
    except ImportError:
        pass

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Tuple, Optional

from mcp_claude_code.server import ClaudeCodeServer

from .server import AuthenticatedMCPServer


def get_vibecode_config_path() -> Path:
    """Get the path to .vibecode.json in the current working directory."""
    return Path.cwd() / ".vibecode.json"


def load_persistent_uuid() -> Optional[str]:
    """Load persistent UUID from .vibecode.json file."""
    config_path = get_vibecode_config_path()
    try:
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get('uuid')
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not read .vibecode.json: {e}", file=sys.stderr)
    return None


def save_persistent_uuid(uuid_value: str) -> None:
    """Save persistent UUID to .vibecode.json file."""
    config_path = get_vibecode_config_path()
    
    # Load existing config or create new one
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            # If file is corrupted, start fresh
            config = {}
    
    # Update UUID
    config['uuid'] = uuid_value
    
    # Save config
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"💾 Saved session UUID to {config_path}", file=sys.stderr)
    except IOError as e:
        print(f"Warning: Could not save .vibecode.json: {e}", file=sys.stderr)


def get_or_create_uuid(reset: bool = False) -> str:
    """Get existing UUID from .vibecode.json or create a new one."""
    # If reset flag is set, force creation of new UUID
    if reset:
        print(f"🔄 Resetting session UUID (--reset-uuid)", file=sys.stderr)
        new_uuid = uuid.uuid4().hex
        save_persistent_uuid(new_uuid)
        return new_uuid
    
    # Try to load existing UUID
    existing_uuid = load_persistent_uuid()
    if existing_uuid:
        print(f"🔄 Using saved session UUID from .vibecode.json", file=sys.stderr)
        return existing_uuid
    
    # Create new UUID
    new_uuid = uuid.uuid4().hex
    print(f"🆕 Generated new session UUID", file=sys.stderr)
    save_persistent_uuid(new_uuid)
    return new_uuid


def check_cloudflared() -> bool:
    """Check if cloudflared is installed and available in PATH."""
    # Common locations for cloudflared
    cloudflared_paths = [
        "cloudflared",  # In PATH
        "/opt/homebrew/bin/cloudflared",  # Homebrew on Apple Silicon
        "/usr/local/bin/cloudflared",  # Homebrew on Intel Mac
        "/usr/bin/cloudflared",  # Linux system install
    ]
    
    for path in cloudflared_paths:
        try:
            subprocess.run([path, "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return False


def run_mcp_server(port: int, path: str, enable_auth: bool = True) -> None:
    """Run the Claude-Code MCP server (blocking)."""
    import logging
    
    # Configure logging for cleaner output
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    # Suppress uvicorn startup messages
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    try:
        if enable_auth:
            # Create authenticated server with OAuth support
            base_url = f"http://localhost:{port}"
            server = AuthenticatedMCPServer(
                name="vibecode-server",
                allowed_paths=["/"],  # Allow full filesystem access for now
                enable_agent_tool=False,
                base_url=base_url
            )
            
            # Run with SSE transport and OAuth authentication
            # Bind to 127.0.0.1 to ensure cloudflared can connect to localhost
            server.run_sse_with_auth(host="127.0.0.1", port=port, path=path)
        else:
            # Fallback to basic MCP server without authentication
            server = ClaudeCodeServer(
                name="vibecode-server",
                allowed_paths=["/"],  # Allow full filesystem access for now
                enable_agent_tool=False
            )
            
            # Run with SSE transport and custom parameters
            # Bind to 127.0.0.1 to ensure cloudflared can connect to localhost
            server.mcp.run(transport="sse", host="127.0.0.1", port=port, path=path)
        
    except Exception as e:
        print(f"Error running MCP server: {e}", file=sys.stderr)
        sys.exit(1)


def start_tunnel(local_url: str, tunnel_name: Optional[str] = None) -> Tuple[str, subprocess.Popen]:
    """
    Runs cloudflared tunnel and returns the publicly accessible URL.
    
    Args:
        local_url: The local URL to tunnel (e.g., http://localhost:8300/path)
        tunnel_name: Optional named tunnel to use (requires Cloudflare account setup)
    
    Returns:
        Tuple of (public_url, process)
    """
    # Pass the full local_url including UUID path to cloudflared
    # This ensures cloudflared forwards requests to the correct endpoint
    # Find cloudflared binary
    cloudflared_paths = [
        "cloudflared",  # In PATH
        "/opt/homebrew/bin/cloudflared",  # Homebrew on Apple Silicon
        "/usr/local/bin/cloudflared",  # Homebrew on Intel Mac
        "/usr/bin/cloudflared",  # Linux system install
    ]
    
    cloudflared_cmd = None
    for path in cloudflared_paths:
        try:
            subprocess.run([path, "--version"], capture_output=True, check=True)
            cloudflared_cmd = path
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    if not cloudflared_cmd:
        raise RuntimeError("cloudflared not found in any expected location")
    
    if tunnel_name:
        # Use named tunnel (persistent domain)
        print(f"Starting cloudflared with URL: {local_url}", file=sys.stderr)
        process = subprocess.Popen(
            [cloudflared_cmd, "tunnel", "--no-autoupdate", "--url", local_url, "run", tunnel_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )
        
        # For named tunnels, the domain follows a predictable pattern
        public_url = f"https://{tunnel_name}.cfargotunnel.com"
        print(f"Using tunnel domain: {public_url}", file=sys.stderr)
        
        return public_url, process
    else:
        # Use quick tunnel (random domain)
        print(f"Starting cloudflared with URL: {local_url}", file=sys.stderr)
        process = subprocess.Popen(
            [cloudflared_cmd, "tunnel", "--no-autoupdate", "--url", local_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )
        
        public_url = None
        # Parse stdout to find the assigned URL
        url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
        
        # Give cloudflared some time to start and output the URL
        start_time = time.time()
        timeout = 30  # 30 seconds timeout
        
        while time.time() - start_time < timeout:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    # Process terminated
                    break
                continue
                
            # Print cloudflared output for debugging
            print(f"[cloudflared] {line.strip()}", file=sys.stderr)
            
            if not public_url:
                match = url_pattern.search(line)
                if match:
                    public_url = match.group(0)
                    break
        
        if not public_url:
            process.terminate()
            raise RuntimeError("Failed to obtain Cloudflare quick tunnel URL within timeout")
        
        return public_url, process


def get_tunnel_domain(cloudflared_cmd: str, tunnel_name: str) -> Optional[str]:
    """Get the domain for a named tunnel."""
    try:
        result = subprocess.run(
            [cloudflared_cmd, "tunnel", "info", tunnel_name],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the output to find the domain
        for line in result.stdout.split('\n'):
            # Look for various domain patterns
            if 'https://' in line:
                # Try to extract domain from patterns like:
                # "https://example.your-domain.com"
                # "https://tunnel-name.cfargotunnel.com" 
                # "https://example.cloudflareaccess.com"
                match = re.search(r'https://([a-zA-Z0-9.-]+(?:\.cfargotunnel\.com|\.cloudflareaccess\.com|\.trycloudflare\.com|[a-zA-Z0-9.-]+))', line)
                if match:
                    return f"https://{match.group(1)}"
        
        # If no domain found in info output, try to construct cfargotunnel domain
        # Most named tunnels get a free subdomain like: tunnel-name.cfargotunnel.com
        return f"https://{tunnel_name}.cfargotunnel.com"
        
    except subprocess.CalledProcessError:
        # If tunnel info fails, try the default cfargotunnel subdomain
        return f"https://{tunnel_name}.cfargotunnel.com"


def list_tunnels() -> list:
    """List available named tunnels."""
    cloudflared_paths = [
        "cloudflared",
        "/opt/homebrew/bin/cloudflared",
        "/usr/local/bin/cloudflared",
        "/usr/bin/cloudflared",
    ]
    
    cloudflared_cmd = None
    for path in cloudflared_paths:
        try:
            subprocess.run([path, "--version"], capture_output=True, check=True)
            cloudflared_cmd = path
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    if not cloudflared_cmd:
        return []
    
    try:
        result = subprocess.run(
            [cloudflared_cmd, "tunnel", "list"],
            capture_output=True,
            text=True,
            check=True
        )
        
        tunnels = []
        lines = result.stdout.split('\n')
        for line in lines[1:]:  # Skip header
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    tunnel_name = parts[1]  # Second column is usually the name
                    tunnels.append(tunnel_name)
        
        return tunnels
    except subprocess.CalledProcessError:
        return []


def ensure_tunnel_exists(cloudflared_cmd: str, preferred_name: str = "vibecode") -> str:
    """Ensure a vibecode tunnel exists, create if needed. Returns tunnel name."""
    try:
        # Check if user is logged in
        result = subprocess.run(
            [cloudflared_cmd, "tunnel", "list"],
            capture_output=True,
            text=True,
            check=False  # Don't raise on error, we'll handle it
        )
        
        if result.returncode != 0:
            # User not logged in or other auth issue
            print("🔐 Cloudflare authentication required for persistent tunnels.")
            print("    Run: cloudflared tunnel login")
            print("    Then try again, or use --quick for temporary tunnel.")
            return None
        
        # Parse existing tunnels
        existing_tunnels = []
        lines = result.stdout.split('\n')
        for line in lines[1:]:  # Skip header
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    tunnel_name = parts[1]
                    existing_tunnels.append(tunnel_name)
        
        # Look for existing vibecode tunnel
        vibecode_tunnels = [t for t in existing_tunnels if t.startswith('vibecode')]
        if vibecode_tunnels:
            print(f"✅ Using existing tunnel: {vibecode_tunnels[0]}")
            return vibecode_tunnels[0]
        
        # Create new tunnel
        import time
        timestamp = str(int(time.time()))[-6:]  # Last 6 digits of timestamp
        tunnel_name = f"{preferred_name}-{timestamp}"
        
        print(f"🚀 Creating persistent tunnel: {tunnel_name}")
        create_result = subprocess.run(
            [cloudflared_cmd, "tunnel", "create", tunnel_name],
            capture_output=True,
            text=True,
            check=False
        )
        
        if create_result.returncode != 0:
            print(f"❌ Failed to create tunnel: {create_result.stderr}")
            return None
        
        print(f"✅ Created tunnel: {tunnel_name}")
        print(f"🌐 Your stable domain: https://{tunnel_name}.cfargotunnel.com")
        return tunnel_name
        
    except Exception as e:
        print(f"Error managing tunnel: {e}")
        return None


def is_authenticated() -> bool:
    """Check if user is authenticated with Cloudflare."""
    cloudflared_paths = [
        "cloudflared",
        "/opt/homebrew/bin/cloudflared", 
        "/usr/local/bin/cloudflared",
        "/usr/bin/cloudflared",
    ]
    
    for path in cloudflared_paths:
        try:
            subprocess.run([path, "--version"], capture_output=True, check=True)
            result = subprocess.run(
                [path, "tunnel", "list"],
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    return False


# Keep backward compatibility
def start_quick_tunnel(local_url: str) -> Tuple[str, subprocess.Popen]:
    """Legacy function for backward compatibility."""
    return start_tunnel(local_url, tunnel_name=None)


def print_simple_setup_guide() -> None:
    """Print simplified one-time setup guide."""
    print("\n" + "="*60)
    print("🚀 VibeCode One-Time Setup")
    print("="*60)
    print()
    print("Get a persistent domain that never changes!")
    print()
    print("💡 Two options:")
    print()
    print("1️⃣  JUST WORKS (Quick tunnel)")
    print("   vibecode start")
    print("   → Gets random domain like: https://abc-123.trycloudflare.com")
    print("   ✅ Zero setup  ❌ Changes every time")
    print()
    print("2️⃣  PERSISTENT DOMAIN (Recommended)")
    print("   Step 1: cloudflared tunnel login")
    print("   Step 2: vibecode start")
    print("   → Gets stable domain like: https://vibecode-123456.cfargotunnel.com")
    print("   ✅ Same domain forever  ✅ Better for claude.ai")
    print()
    print("🎯 For claude.ai, use option 2 (persistent domain)")
    print("   Your URL won't change, so you only configure claude.ai once!")
    print()
    print("📚 Need more details? Run: vibecode tunnel guide")
    print()


def print_tunnel_setup_guide() -> None:
    """Print guide for setting up persistent Cloudflare tunnels."""
    print("\n" + "="*70)
    print("🌩️  Setting up Persistent Cloudflare Tunnels")
    print("="*70)
    print()
    print("Persistent tunnels give you a stable domain that doesn't change between")
    print("launches. Choose from two options:")
    print()
    
    print("🔥 OPTION 1: Free Cloudflare Subdomain (Recommended)")
    print("="*50)
    print("Get a free subdomain like: https://my-tunnel.cfargotunnel.com")
    print()
    print("1. Create a Cloudflare account at https://dash.cloudflare.com")
    print()
    print("2. Login to cloudflared:")
    print("   cloudflared tunnel login")
    print()
    print("3. Create a named tunnel:")
    print("   cloudflared tunnel create my-mcp-server")
    print()
    print("4. Use your tunnel (automatically gets .cfargotunnel.com subdomain):")
    print("   vibecode start --tunnel my-mcp-server")
    print("   # → https://my-mcp-server.cfargotunnel.com")
    print()
    
    print("🏠 OPTION 2: Your Own Domain")
    print("="*30)
    print("Use your own domain like: https://mcp.yourdomain.com")
    print()
    print("Follow steps 1-3 above, then:")
    print()
    print("4. Add your domain to Cloudflare and create DNS record:")
    print("   cloudflared tunnel route dns my-mcp-server mcp.yourdomain.com")
    print()
    print("5. Use your custom domain:")
    print("   vibecode start --tunnel my-mcp-server")
    print("   # → https://mcp.yourdomain.com")
    print()
    
    print("🔗 Documentation:")
    print("   https://developers.cloudflare.com/cloudflare-one/connections/connect-apps")
    print()
    print("💡 Benefits of persistent tunnels:")
    print("   • Same domain every time")
    print("   • Better security and monitoring") 
    print("   • No random URL changes")
    print("   • Production-ready uptime guarantee")
    print("   • Free Cloudflare subdomain available")
    print()


def print_instructions(url: str, enable_auth: bool = True) -> None:
    """Print setup instructions for the user."""
    print("\n" + "="*60, file=sys.stderr)
    print("🚀 VibeCode MCP Server Ready", file=sys.stderr)
    print("="*60, file=sys.stderr)
    print(f"\n📡 URL: {url}", file=sys.stderr)
    
    print("\n🔗 Add to Claude.ai:", file=sys.stderr)
    print("  1. Copy the URL above", file=sys.stderr)
    print("  2. Add as MCP server (transport: sse)", file=sys.stderr)
    print("  3. Authentication handled automatically", file=sys.stderr)
    
    # Check if this is a quick tunnel (random domain)
    if "trycloudflare.com" in url:
        print("\n💡 For persistent domain: vibecode tunnel setup", file=sys.stderr)
    
    print("\nPress Ctrl+C to stop\n", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vibecode",
        description="Start MCP server for Claude-Code with automatic Cloudflare tunneling"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    start_parser = subparsers.add_parser("start", help="Start MCP server and Cloudflare tunnel")
    start_parser.add_argument("--port", type=int, default=8300, help="Port to run the local server on (default: 8300)")
    start_parser.add_argument("--no-tunnel", action="store_true", help="Run without Cloudflare tunnel (local only)")
    start_parser.add_argument("--no-auth", action="store_true", help="Disable OAuth authentication (for testing only)")
    start_parser.add_argument("--tunnel", type=str, help="Use specific named tunnel (optional)")
    start_parser.add_argument("--quick", action="store_true", help="Use quick tunnel (random domain) instead of persistent")
    start_parser.add_argument("--reset-uuid", action="store_true", help="Generate new session UUID (creates new MCP URL path)")
    
    # Add simple setup command for first-time users
    setup_parser = subparsers.add_parser("setup", help="One-time setup for persistent domains")
    
    # Add tunnel management commands  
    tunnel_parser = subparsers.add_parser("tunnel", help="Manage Cloudflare tunnels")
    tunnel_subparsers = tunnel_parser.add_subparsers(dest="tunnel_command", required=True)
    
    list_parser = tunnel_subparsers.add_parser("list", help="List available named tunnels")
    guide_parser = tunnel_subparsers.add_parser("guide", help="Setup guide for creating named tunnels")

    args = parser.parse_args()
    
    if args.command == "start":
        # Check if cloudflared is installed (unless running local only)
        if not args.no_tunnel and not check_cloudflared():
            print("Error: cloudflared is not installed.", file=sys.stderr)
            print("\nTo install cloudflared:", file=sys.stderr)
            print("  - macOS: brew install cloudflared", file=sys.stderr)
            print("  - Linux: See https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation", file=sys.stderr)
            print("  - Or run with --no-tunnel for local-only mode", file=sys.stderr)
            sys.exit(1)
        
        # Get or create persistent UUID path
        uuid_hex = get_or_create_uuid(reset=args.reset_uuid)
        uuid_path = f"/{uuid_hex}"
        
        # Start the MCP server in a daemon thread
        enable_auth = not args.no_auth
        print(f"Starting MCP server on port {args.port}...", file=sys.stderr)
        server_thread = threading.Thread(
            target=run_mcp_server, 
            args=(args.port, uuid_path, enable_auth), 
            daemon=True
        )
        server_thread.start()
        
        # Give the server more time to start and become ready
        print("Waiting for server to become ready...", file=sys.stderr)
        time.sleep(3)
        
        # Verify the server is actually listening on the port
        import socket
        max_retries = 5
        for i in range(max_retries):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    result = s.connect_ex(('127.0.0.1', args.port))
                    if result == 0:
                        print(f"Server is ready on port {args.port}", file=sys.stderr)
                        break
                    else:
                        print(f"Server not ready yet, retrying ({i+1}/{max_retries})...", file=sys.stderr)
                        time.sleep(2)
            except Exception as e:
                print(f"Server check failed ({i+1}/{max_retries}): {e}", file=sys.stderr)
                time.sleep(2)
        else:
            print("Warning: Could not verify server is ready, proceeding anyway...", file=sys.stderr)
        
        if args.no_tunnel:
            # Local-only mode
            local_url = f"http://localhost:{args.port}{uuid_path}"
            print(f"\nMCP server running locally at: {local_url}")
            print("Press Ctrl+C to stop.")
            try:
                # Keep running until interrupted
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down...")
                sys.exit(0)
        else:
            # Start Cloudflare tunnel
            # NOTE: cloudflared should tunnel to the base server URL, not the UUID path
            # The UUID path is handled by our server internally
            base_local_url = f"http://localhost:{args.port}"
            
            try:
                # Determine tunnel strategy
                if hasattr(args, 'quick') and args.quick:
                    # User explicitly wants quick tunnel
                    print("Starting quick tunnel...", file=sys.stderr)
                    public_url, tunnel_process = start_tunnel(base_local_url, tunnel_name=None)
                elif hasattr(args, 'tunnel') and args.tunnel:
                    # User specified a specific tunnel
                    print(f"Using tunnel: {args.tunnel}", file=sys.stderr)
                    public_url, tunnel_process = start_tunnel(base_local_url, tunnel_name=args.tunnel)
                else:
                    # Default: try to use persistent tunnel
                    cloudflared_cmd = None
                    for path in ["cloudflared", "/opt/homebrew/bin/cloudflared", "/usr/local/bin/cloudflared", "/usr/bin/cloudflared"]:
                        try:
                            subprocess.run([path, "--version"], capture_output=True, check=True)
                            cloudflared_cmd = path
                            break
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            continue
                    
                    if cloudflared_cmd and is_authenticated():
                        # Try to use/create persistent tunnel
                        tunnel_name = ensure_tunnel_exists(cloudflared_cmd)
                        if tunnel_name:
                            print(f"Using persistent tunnel: {tunnel_name}", file=sys.stderr)
                            public_url, tunnel_process = start_tunnel(base_local_url, tunnel_name=tunnel_name)
                        else:
                            # Fall back to quick tunnel
                            print("Falling back to quick tunnel...", file=sys.stderr)
                            public_url, tunnel_process = start_tunnel(base_local_url, tunnel_name=None)
                    else:
                        # Not authenticated or no cloudflared, use quick tunnel
                        print("Starting quick tunnel...", file=sys.stderr)
                        public_url, tunnel_process = start_tunnel(base_local_url, tunnel_name=None)
                        
            except Exception as e:
                print(f"Error starting Cloudflare tunnel: {e}", file=sys.stderr)
                sys.exit(1)
            
            full_public_url = f"{public_url}{uuid_path}"
            
            # Print URL to stdout for easy capture
            print(full_public_url)
            
            # Print instructions to stderr
            print_instructions(full_public_url, enable_auth)
            
            try:
                # Wait for tunnel process to end (until user interrupts)
                tunnel_process.wait()
            except KeyboardInterrupt:
                print("\nShutting down...")
                tunnel_process.terminate()
                tunnel_process.wait(timeout=5)
                sys.exit(0)
    
    elif args.command == "setup":
        print_simple_setup_guide()
    
    elif args.command == "tunnel":
        if args.tunnel_command == "list":
            tunnels = list_tunnels()
            if tunnels:
                print("Available named tunnels:")
                for tunnel in tunnels:
                    print(f"  • {tunnel}")
            else:
                print("No named tunnels found.")
                print("Run 'vibecode setup' to get started.")
        
        elif args.tunnel_command == "guide":
            print_tunnel_setup_guide()


if __name__ == "__main__":
    main()