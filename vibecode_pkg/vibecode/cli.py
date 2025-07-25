import argparse
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from typing import Tuple, Optional

try:
    from mcp_claude_code.server import ClaudeCodeServer
except ImportError:
    print("Error: mcp-claude-code is not installed. Please install vibecode properly.")
    sys.exit(1)


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


def run_mcp_server(port: int, path: str) -> None:
    """Run the Claude-Code MCP server (blocking)."""
    try:
        # Create the server instance with proper configuration
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


def start_quick_tunnel(local_url: str) -> Tuple[str, subprocess.Popen]:
    """
    Runs cloudflared quick tunnel and returns the publicly accessible URL.
    Requires that 'cloudflared' binary is installed.
    """
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
    
    # Launch cloudflared tunnel --url http://localhost:<port><path>
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


def print_instructions(url: str) -> None:
    """Print setup instructions for the user."""
    print("\n" + "="*60)
    print("🚀 Claude-Code MCP server is running!")
    print("="*60)
    print(f"\n📡 Public URL: {url}\n")
    print("To use with ChatGPT or Claude:")
    print("1. Copy the URL above")
    print("2. Add it to your MCP configuration")
    print("3. Set transport type to: sse")
    print("\n⚠️  Note: This is a temporary tunnel that will expire when stopped.")
    print("Press Ctrl+C to stop the server and tunnel.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vibecode",
        description="Start MCP server for Claude-Code with automatic Cloudflare tunneling"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    start_parser = subparsers.add_parser("start", help="Start MCP server and Cloudflare quick tunnel")
    start_parser.add_argument("--port", type=int, default=8300, help="Port to run the local server on (default: 8300)")
    start_parser.add_argument("--no-tunnel", action="store_true", help="Run without Cloudflare tunnel (local only)")

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
        
        # Generate random UUID path
        uuid_path = f"/{uuid.uuid4().hex}"
        
        # Start the MCP server in a daemon thread
        print(f"Starting MCP server on port {args.port}...")
        server_thread = threading.Thread(
            target=run_mcp_server, 
            args=(args.port, uuid_path), 
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
            print(f"Starting Cloudflare quick tunnel...")
            
            try:
                public_url, tunnel_process = start_quick_tunnel(local_url)
            except Exception as e:
                print(f"Error starting Cloudflare tunnel: {e}", file=sys.stderr)
                sys.exit(1)
            
            full_public_url = f"{public_url}{uuid_path}"
            print_instructions(full_public_url)
            
            try:
                # Wait for tunnel process to end (until user interrupts)
                tunnel_process.wait()
            except KeyboardInterrupt:
                print("\nShutting down...")
                tunnel_process.terminate()
                tunnel_process.wait(timeout=5)
                sys.exit(0)


if __name__ == "__main__":
    main()