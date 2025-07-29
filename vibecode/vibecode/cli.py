# Suppress all warnings before any imports
import warnings
import os
warnings.simplefilter("ignore")
os.environ["PYDANTIC_DISABLE_WARNINGS"] = "1"

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import uuid
import yaml
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


def save_tunnel_info(tunnel_url: str, tunnel_process_pid: int, tunnel_name: Optional[str] = None) -> None:
    """Save tunnel information to .vibecode.json file."""
    config_path = get_vibecode_config_path()
    
    # Load existing config
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            config = {}
    
    # Update tunnel info
    config['tunnel'] = {
        'url': tunnel_url,
        'pid': tunnel_process_pid,
        'name': tunnel_name,
        'created_at': time.time()
    }
    
    # Save config
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"💾 Saved tunnel info to {config_path}", file=sys.stderr)
    except IOError as e:
        print(f"Warning: Could not save tunnel info: {e}", file=sys.stderr)


def load_tunnel_info() -> Optional[dict]:
    """Load tunnel information from .vibecode.json file."""
    config_path = get_vibecode_config_path()
    try:
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get('tunnel')
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not read tunnel info: {e}", file=sys.stderr)
    return None


def is_tunnel_process_alive(pid: int) -> bool:
    """Check if a tunnel process is still running."""
    try:
        import psutil
        # Use psutil for cross-platform process checking
        process = psutil.Process(pid)
        return process.is_running()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False


def get_existing_tunnel() -> Optional[Tuple[str, int]]:
    """Get existing tunnel info if available and running."""
    tunnel_info = load_tunnel_info()
    if not tunnel_info:
        return None
    
    pid = tunnel_info.get('pid')
    url = tunnel_info.get('url')
    
    if not pid or not url:
        return None
    
    # Check if process is still alive
    if is_tunnel_process_alive(pid):
        print(f"🔄 Found existing tunnel: {url} (PID: {pid})", file=sys.stderr)
        return url, pid
    else:
        print(f"⚠️ Previous tunnel process (PID: {pid}) is no longer running", file=sys.stderr)
        return None


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
            server.run_sse_with_auth(host="0.0.0.0", port=port, path=path)
        else:
            # Fallback to basic MCP server without authentication
            server = ClaudeCodeServer(
                name="vibecode-server",
                allowed_paths=["/"],  # Allow full filesystem access for now
                enable_agent_tool=False
            )
            
            # Run with SSE transport and custom parameters
            server.mcp.run(transport="sse", host="0.0.0.0", port=port, path=path)
        
    except Exception as e:
        print(f"Error running MCP server: {e}", file=sys.stderr)
        sys.exit(1)


def start_tunnel(local_url: str, tunnel_name: Optional[str] = None, reuse_existing: bool = True) -> Tuple[str, subprocess.Popen]:
    """
    Runs cloudflared tunnel and returns the publicly accessible URL.
    
    Args:
        local_url: The local URL to tunnel (e.g., http://localhost:8300/path)
        tunnel_name: Optional named tunnel to use (requires Cloudflare account setup)
        reuse_existing: Whether to reuse existing tunnel process if available
    
    Returns:
        Tuple of (public_url, process)
    """
    # Check for existing tunnel if reuse is enabled
    if reuse_existing:
        existing_tunnel = get_existing_tunnel()
        if existing_tunnel:
            url, pid = existing_tunnel
            # Create a mock process object that references the existing process
            import psutil
            try:
                existing_process = psutil.Process(pid)
                # Create a minimal subprocess.Popen-like object
                class ExistingProcess:
                    def __init__(self, pid):
                        self.pid = pid
                        self._process = psutil.Process(pid)
                    
                    def wait(self):
                        return self._process.wait()
                    
                    def terminate(self):
                        self._process.terminate()
                    
                    def poll(self):
                        if self._process.is_running():
                            return None
                        return self._process.returncode
                
                return url, ExistingProcess(pid)
            except (psutil.NoSuchProcess, ImportError):
                print(f"⚠️ Existing tunnel process not accessible, creating new one", file=sys.stderr)
                pass
    # Import required modules
    import re
    from urllib.parse import urlparse
    
    # Extract base URL without path for cloudflared
    # cloudflared should only get the host:port, not the UUID path
    parsed = urlparse(local_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
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
        print(f"Starting cloudflared with base URL: {base_url}", file=sys.stderr)
        process = subprocess.Popen(
            [cloudflared_cmd, "tunnel", "run", "--no-autoupdate", "--url", base_url, tunnel_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )
        
        # For named tunnels, we need to check if DNS is configured
        # The .cfargotunnel.com subdomain doesn't automatically resolve without additional setup
        potential_url = f"https://{tunnel_name}.cfargotunnel.com"
        
        # Try to resolve the domain to check if DNS is configured
        import socket
        try:
            socket.gethostbyname(f"{tunnel_name}.cfargotunnel.com")
            public_url = potential_url
            print(f"✅ Using configured tunnel domain: {public_url}", file=sys.stderr)
        except socket.gaierror:
            # DNS not configured, try to configure it automatically or provide guidance
            print(f"⚠️ Named tunnel created but DNS not configured for {potential_url}", file=sys.stderr)
            print(f"🔧 Attempting to configure DNS automatically...", file=sys.stderr)
            
            try:
                # Find cloudflared command (reuse the same logic from below)
                cloudflared_paths = [
                    "cloudflared",  # In PATH
                    "/opt/homebrew/bin/cloudflared",  # Homebrew on Apple Silicon
                    "/usr/local/bin/cloudflared",  # Homebrew on Intel Mac
                    "/usr/bin/cloudflared",  # Linux system install
                ]
                
                dns_cloudflared_cmd = None
                for path in cloudflared_paths:
                    try:
                        subprocess.run([path, "--version"], capture_output=True, check=True)
                        dns_cloudflared_cmd = path
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue
                
                if not dns_cloudflared_cmd:
                    raise RuntimeError("cloudflared not found for DNS configuration")
                
                # Try to configure DNS route automatically
                # Use the correct domain format for persistent tunnels
                domain_name = f"{tunnel_name}.vibebrowser.app"
                dns_result = subprocess.run(
                    [dns_cloudflared_cmd, "tunnel", "route", "dns", tunnel_name, domain_name],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if dns_result.returncode == 0:
                    print(f"✅ DNS configured successfully", file=sys.stderr)
                    
                    # Try to extract the actual domain from the DNS configuration output
                    actual_domain = None
                    dns_output = dns_result.stdout + dns_result.stderr
                    
                    # Look for patterns like "Added CNAME domain.com" or "domain.com is already configured"
                    # re module already imported at top of function
                    domain_patterns = [
                        r'Added CNAME\s+([^\s]+)',
                        r'([^\s]+)\s+is already configured',
                        r'INF\s+([^\s]+)\s+is already configured',
                        r'which will route to this tunnel'  # Match the line with route info
                    ]
                    
                    for pattern in domain_patterns:
                        match = re.search(pattern, dns_output)
                        if match:
                            actual_domain = match.group(1)
                            break
                    
                    if actual_domain:
                        # Clean up domain (remove trailing periods)
                        actual_domain = actual_domain.rstrip('.')
                        public_url = f"https://{actual_domain}"
                        print(f"🌐 Detected configured domain: {public_url}", file=sys.stderr)
                    else:
                        # If we can't parse the domain, use the configured domain name
                        public_url = f"https://{domain_name}"
                        print(f"🌐 Using configured domain: {public_url}", file=sys.stderr)
                        
                        # Test if the domain resolves
                        domain_to_test = actual_domain if actual_domain else domain_name
                        try:
                            socket.gethostbyname(domain_to_test)
                            print(f"✅ Domain resolves successfully - using {public_url}", file=sys.stderr)
                        except socket.gaierror:
                            print(f"⏳ Waiting for DNS propagation...", file=sys.stderr)
                            time.sleep(3)
                            try:
                                socket.gethostbyname(domain_to_test)
                                print(f"✅ DNS propagation successful - using {public_url}", file=sys.stderr)
                            except socket.gaierror:
                                print(f"⚠️ DNS propagation still in progress - this may take up to 5 minutes", file=sys.stderr)
                                print(f"🚀 For immediate access, falling back to quick tunnel...", file=sys.stderr)
                                
                                # Stop the named tunnel and fall back to quick tunnel
                                process.terminate()
                                process.wait(timeout=5)
                                
                                # Retry with quick tunnel
                                return start_tunnel(local_url, tunnel_name=None, reuse_existing=False)
                else:
                    print(f"❌ Auto-DNS configuration failed: {dns_result.stderr.strip()}", file=sys.stderr)
                    print(f"🔧 Manual configuration needed:", file=sys.stderr)
                    print(f"   cloudflared tunnel route dns {tunnel_name} {tunnel_name}.cfargotunnel.com", file=sys.stderr)
                    print(f"📝 Or use a custom domain: cloudflared tunnel route dns {tunnel_name} yourdomain.com", file=sys.stderr)
                    print(f"🚀 For now, falling back to quick tunnel...", file=sys.stderr)
                    
                    # Stop the named tunnel and fall back to quick tunnel
                    process.terminate()
                    process.wait(timeout=5)
                    
                    # Retry with quick tunnel
                    return start_tunnel(local_url, tunnel_name=None, reuse_existing=False)
                    
            except Exception as e:
                print(f"❌ Error configuring DNS: {e}", file=sys.stderr)
                print(f"🚀 Falling back to quick tunnel...", file=sys.stderr)
                
                # Stop the named tunnel and fall back to quick tunnel
                process.terminate()
                process.wait(timeout=5)
                
                # Retry with quick tunnel
                return start_tunnel(local_url, tunnel_name=None, reuse_existing=False)
        
        # Save tunnel info for reuse
        save_tunnel_info(public_url, process.pid, tunnel_name)
        
        return public_url, process
    else:
        # Use quick tunnel (random domain)
        print(f"Starting cloudflared with base URL: {base_url}", file=sys.stderr)
        process = subprocess.Popen(
            [cloudflared_cmd, "tunnel", "--no-autoupdate", "--url", base_url],
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
        
        # Save tunnel info for reuse (quick tunnels are temporary but still useful for short-term reuse)
        save_tunnel_info(public_url, process.pid, None)
        
        return public_url, process


def start_tunnel_with_config(local_url: str, config_path: str, reuse_existing: bool = True) -> Tuple[str, subprocess.Popen]:
    """
    Start a tunnel using a config file.
    
    Args:
        local_url: The local URL to tunnel (e.g., http://localhost:8300/path)
        config_path: Path to the cloudflared config.yml file
        reuse_existing: Whether to reuse existing tunnel process if available
    
    Returns:
        Tuple of (public_url, process)
    """
    # Check for existing config-based tunnel if reuse is enabled
    if reuse_existing:
        existing_tunnel = get_existing_tunnel()
        if existing_tunnel:
            url, pid = existing_tunnel
            # Only reuse if it's NOT a quick tunnel (trycloudflare.com)
            if "trycloudflare.com" not in url:
                # Create a mock process object that references the existing process
                import psutil
                try:
                    existing_process = psutil.Process(pid)
                    # Create a minimal subprocess.Popen-like object
                    class ExistingProcess:
                        def __init__(self, pid):
                            self.pid = pid
                            self._process = psutil.Process(pid)
                        
                        def wait(self):
                            return self._process.wait()
                        
                        def terminate(self):
                            self._process.terminate()
                        
                        def poll(self):
                            if self._process.is_running():
                                return None
                            return self._process.returncode
                    
                    print(f"♻️ Reusing existing persistent tunnel: {url}", file=sys.stderr)
                    return url, ExistingProcess(pid)
                except (psutil.NoSuchProcess, ImportError):
                    print(f"⚠️ Existing tunnel process not accessible, creating new one", file=sys.stderr)
                    pass
            else:
                print(f"🔄 Replacing quick tunnel with persistent tunnel", file=sys.stderr)
                # Stop the quick tunnel first
                import psutil
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                    process.wait(timeout=5)
                except (psutil.NoSuchProcess, ImportError, psutil.TimeoutExpired):
                    pass

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
    
    # Start tunnel using config file
    print(f"Starting cloudflared with config: {config_path}", file=sys.stderr)
    process = subprocess.Popen(
        [cloudflared_cmd, "tunnel", "--config", config_path, "run"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
    )
    
    # For config-based tunnels, we need to determine the public URL
    # This requires either a custom domain or the tunnel's auto-generated domain
    
    # For now, we'll use a placeholder URL that users need to configure
    # In practice, users would set up their own domain DNS
    from urllib.parse import urlparse
    parsed = urlparse(local_url)
    uuid_path = parsed.path
    
    # Read tunnel info from config to get tunnel ID
    import yaml
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            tunnel_id = config.get('tunnel')
            if tunnel_id:
                # Use the auto-generated cloudflare domain
                public_url = f"https://{tunnel_id}.cfargotunnel.com"
                print(f"📡 Tunnel URL: {public_url}{uuid_path}", file=sys.stderr)
                print(f"⚠️  To use a custom domain, configure DNS:", file=sys.stderr)
                print(f"    cloudflared tunnel route dns <tunnel-name> yourdomain.com", file=sys.stderr)
                
                # Save tunnel info for reuse
                save_tunnel_info(public_url, process.pid, None)
                
                return public_url, process
    except (ImportError, yaml.YAMLError, FileNotFoundError):
        pass
    
    # Fallback - return a placeholder
    public_url = "https://configure-your-domain.example.com"
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


def check_cloudflare_domain_setup(cloudflared_cmd: str) -> Optional[str]:
    """Check if user has a Cloudflare-managed domain available for persistent tunnels."""
    try:
        # Try to list zones to see if user has domains
        result = subprocess.run(
            [cloudflared_cmd, "tunnel", "route", "dns", "--help"],
            capture_output=True,
            text=True,
            check=False
        )
        
        # This is a simple check - in a real implementation, we'd check for actual domains
        # For now, we'll assume users need to manually configure their domains
        return None
        
    except Exception:
        return None


def create_tunnel_config(tunnel_name: str, tunnel_id: str, local_url: str, custom_domain: Optional[str] = None) -> str:
    """Create a config.yml file for the tunnel."""
    config_dir = Path.home() / ".cloudflared"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config.yml"
    
    # Extract port from local_url
    from urllib.parse import urlparse
    parsed = urlparse(local_url)
    service_url = f"http://localhost:{parsed.port}"
    
    config_content = f"""tunnel: {tunnel_id}
credentials-file: {config_dir}/{tunnel_id}.json

ingress:"""
    
    if custom_domain:
        config_content += f"""
  - hostname: {custom_domain}
    service: {service_url}"""
    
    config_content += f"""
  - service: {service_url}  # Default catch-all rule
"""
    
    with open(config_file, 'w') as f:
        f.write(config_content)
    
    return str(config_file)


def ensure_tunnel_exists(cloudflared_cmd: str, preferred_name: str = "vibecode") -> Optional[tuple]:
    """Ensure a vibecode tunnel exists, create if needed. Returns (tunnel_name, tunnel_id, config_path)."""
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
            print("🔐 Cloudflare authentication required for persistent tunnels.", file=sys.stderr)
            print("    Run: cloudflared tunnel login", file=sys.stderr)
            print("    Then try again, or use --quick for temporary tunnel.", file=sys.stderr)
            return None
        
        # Parse existing tunnels
        existing_tunnels = []
        lines = result.stdout.split('\n')
        for line in lines[1:]:  # Skip header
            if line.strip():
                parts = line.split()
                if len(parts) >= 3:
                    tunnel_id = parts[0]
                    tunnel_name = parts[1]
                    existing_tunnels.append((tunnel_name, tunnel_id))
        
        # Look for existing vibecode tunnel
        vibecode_tunnels = [(name, id_) for name, id_ in existing_tunnels if name.startswith('vibecode')]
        if vibecode_tunnels:
            tunnel_name, tunnel_id = vibecode_tunnels[0]
            print(f"✅ Using existing tunnel: {tunnel_name}", file=sys.stderr)
            return tunnel_name, tunnel_id
        
        # Create new tunnel
        import time
        timestamp = str(int(time.time()))[-6:]  # Last 6 digits of timestamp
        tunnel_name = f"{preferred_name}-{timestamp}"
        
        print(f"🚀 Creating persistent tunnel: {tunnel_name}", file=sys.stderr)
        create_result = subprocess.run(
            [cloudflared_cmd, "tunnel", "create", tunnel_name],
            capture_output=True,
            text=True,
            check=False
        )
        
        if create_result.returncode != 0:
            print(f"❌ Failed to create tunnel: {create_result.stderr}", file=sys.stderr)
            return None
        
        # Extract tunnel ID from creation output
        tunnel_id = None
        for line in create_result.stderr.split('\n'):
            if 'Created tunnel' in line and 'with id' in line:
                # Extract ID from line like "Created tunnel vibecode-123456 with id abc-def-ghi"
                parts = line.split()
                if 'id' in parts:
                    id_index = parts.index('id')
                    if id_index + 1 < len(parts):
                        tunnel_id = parts[id_index + 1]
                        break
        
        if not tunnel_id:
            print(f"⚠️ Could not extract tunnel ID from creation output", file=sys.stderr)
            return None
        
        print(f"✅ Created tunnel: {tunnel_name} (ID: {tunnel_id})", file=sys.stderr)
        return tunnel_name, tunnel_id
        
    except Exception as e:
        print(f"Error managing tunnel: {e}", file=sys.stderr)
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
    start_parser.add_argument("--no-reuse", action="store_true", help="Don't reuse existing tunnels, create new ones")
    
    # Add simple setup command for first-time users
    setup_parser = subparsers.add_parser("setup", help="One-time setup for persistent domains")
    
    # Add tunnel management commands  
    tunnel_parser = subparsers.add_parser("tunnel", help="Manage Cloudflare tunnels")
    tunnel_subparsers = tunnel_parser.add_subparsers(dest="tunnel_command", required=True)
    
    list_parser = tunnel_subparsers.add_parser("list", help="List available named tunnels")
    guide_parser = tunnel_subparsers.add_parser("guide", help="Setup guide for creating named tunnels")
    status_parser = tunnel_subparsers.add_parser("status", help="Show status of current tunnel")
    stop_parser = tunnel_subparsers.add_parser("stop", help="Stop running tunnel")

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
        
        # Give the server a moment to start
        time.sleep(1)
        
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
            local_url = f"http://localhost:{args.port}{uuid_path}"
            
            try:
                # Determine tunnel reuse preference
                reuse_existing = not args.no_reuse
                
                # Determine tunnel strategy
                if hasattr(args, 'quick') and args.quick:
                    # User explicitly wants quick tunnel
                    print("Starting quick tunnel...", file=sys.stderr)
                    public_url, tunnel_process = start_tunnel(local_url, tunnel_name=None, reuse_existing=reuse_existing)
                elif hasattr(args, 'tunnel') and args.tunnel:
                    # User specified a specific tunnel
                    print(f"Using tunnel: {args.tunnel}", file=sys.stderr)
                    public_url, tunnel_process = start_tunnel(local_url, tunnel_name=args.tunnel, reuse_existing=reuse_existing)
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
                        # Try to use/create persistent tunnel with config
                        tunnel_info = ensure_tunnel_exists(cloudflared_cmd)
                        if tunnel_info:
                            tunnel_name, tunnel_id = tunnel_info
                            print(f"Using persistent tunnel: {tunnel_name}", file=sys.stderr)
                            
                            # Create config file for this tunnel
                            config_path = create_tunnel_config(tunnel_name, tunnel_id, local_url)
                            print(f"📝 Created tunnel config: {config_path}", file=sys.stderr)
                            
                            # Use config-based tunnel
                            public_url, tunnel_process = start_tunnel_with_config(local_url, config_path, reuse_existing=reuse_existing)
                        else:
                            # Fall back to quick tunnel
                            print("Falling back to quick tunnel...", file=sys.stderr)
                            public_url, tunnel_process = start_tunnel(local_url, tunnel_name=None, reuse_existing=reuse_existing)
                    else:
                        # Not authenticated or no cloudflared, use quick tunnel
                        print("Starting quick tunnel...", file=sys.stderr)
                        public_url, tunnel_process = start_tunnel(local_url, tunnel_name=None, reuse_existing=reuse_existing)
                        
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
        
        elif args.tunnel_command == "status":
            tunnel_info = load_tunnel_info()
            if not tunnel_info:
                print("No tunnel information found.")
                print("Start a tunnel with: vibecode start")
            else:
                url = tunnel_info.get('url')
                pid = tunnel_info.get('pid')
                name = tunnel_info.get('name')
                created_at = tunnel_info.get('created_at')
                
                print(f"Tunnel Status:")
                print(f"  URL: {url}")
                print(f"  PID: {pid}")
                print(f"  Name: {name if name else 'Quick tunnel'}")
                
                if created_at:
                    import datetime
                    created_time = datetime.datetime.fromtimestamp(created_at)
                    print(f"  Created: {created_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                if pid and is_tunnel_process_alive(pid):
                    print(f"  Status: ✅ Running")
                else:
                    print(f"  Status: ❌ Not running")
        
        elif args.tunnel_command == "stop":
            tunnel_info = load_tunnel_info()
            if not tunnel_info:
                print("No tunnel information found.")
            else:
                pid = tunnel_info.get('pid')
                url = tunnel_info.get('url')
                
                if not pid:
                    print("No tunnel process ID found.")
                elif not is_tunnel_process_alive(pid):
                    print(f"Tunnel process (PID: {pid}) is already stopped.")
                else:
                    try:
                        import psutil
                        process = psutil.Process(pid)
                        
                        # Try graceful termination first
                        process.terminate()
                        time.sleep(2)  # Give it time to terminate gracefully
                        
                        if is_tunnel_process_alive(pid):
                            # Force kill if still running
                            process.kill()
                            print(f"Force stopped tunnel process (PID: {pid})")
                        else:
                            print(f"Stopped tunnel process (PID: {pid})")
                        
                        # Clear tunnel info since we stopped it
                        config_path = get_vibecode_config_path()
                        if config_path.exists():
                            try:
                                with open(config_path, 'r') as f:
                                    config = json.load(f)
                                if 'tunnel' in config:
                                    del config['tunnel']
                                    with open(config_path, 'w') as f:
                                        json.dump(config, f, indent=2)
                                    print("Cleared tunnel information.")
                            except (json.JSONDecodeError, IOError):
                                pass
                                
                    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as e:
                        print(f"Error stopping tunnel: {e}")


if __name__ == "__main__":
    main()