#!/usr/bin/env python3
"""Verification test to confirm that the --quick tunnel URL parsing fix works."""

import subprocess
import sys
import time
import re
import pytest


def test_quick_tunnel_url_parsing_fix():
    """Test that vibecode start --quick now successfully parses tunnel URLs."""
    
    print("🔍 Verifying quick tunnel URL parsing fix...")
    
    port = 8620
    proc = subprocess.Popen([
        sys.executable, '-m', 'vibecode.cli', 'start', '--quick', '--port', str(port)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    
    try:
        # Key indicators we're looking for
        server_started = False
        cloudflared_started = False
        tunnel_url_found = False
        tunnel_url = None
        url_parsing_success = False
        
        # Monitor output for up to 90 seconds (enough time for tunnel creation)
        start_time = time.time()
        
        while time.time() - start_time < 90:
            # Check stderr (where most output goes)
            line = proc.stderr.readline()
            if line:
                line = line.strip()
                
                # Track server startup
                if 'Server is ready on port' in line:
                    server_started = True
                    print(f"✅ Server started successfully")
                
                # Track cloudflared startup
                if 'Starting cloudflared' in line:
                    cloudflared_started = True
                    print(f"✅ Cloudflared started successfully")
                
                # Look for successful URL parsing
                if '✅ Found tunnel URL:' in line:
                    url_parsing_success = True
                    url_match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
                    if url_match:
                        tunnel_url = url_match.group(0)
                        tunnel_url_found = True
                        print(f"✅ URL parsing fix successful: {tunnel_url}")
                        break
                
                # Also look for the final URL display
                if 'trycloudflare.com/' in line and 'URL:' in line:
                    tunnel_url_found = True
                    print(f"✅ Complete tunnel URL displayed successfully")
                    break
            
            # Check if process terminated unexpectedly
            if proc.poll() is not None:
                print("❌ Process terminated unexpectedly")
                break
                
            time.sleep(0.1)
    
    finally:
        # Cleanup
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    
    # Verification
    print(f"\n📊 Test Results:")
    print(f"   Server started: {server_started}")
    print(f"   Cloudflared started: {cloudflared_started}")
    print(f"   URL parsing successful: {url_parsing_success}")
    print(f"   Tunnel URL found: {tunnel_url_found}")
    if tunnel_url:
        print(f"   Tunnel URL: {tunnel_url}")
    
    # The core fix should ensure that:
    # 1. Server starts successfully
    # 2. Cloudflared starts successfully  
    # 3. URL parsing works (either we see the success message or final URL)
    
    success = server_started and cloudflared_started and (url_parsing_success or tunnel_url_found)
    
    if success:
        print(f"\n🎉 SUCCESS: Quick tunnel URL parsing fix is working!")
        print(f"   The original issue 'vibecode start --quick fails to open working tunnel' is RESOLVED")
        print(f"   Users can now successfully get tunnel URLs from vibecode start --quick")
    else:
        print(f"\n❌ FAILURE: URL parsing fix needs more work")
        
        if not server_started:
            print(f"   Issue: Server failed to start")
        if not cloudflared_started:
            print(f"   Issue: Cloudflared failed to start")
        if not url_parsing_success and not tunnel_url_found:
            print(f"   Issue: URL parsing still not working")
    
    return success


if __name__ == "__main__":
    success = test_quick_tunnel_url_parsing_fix()
    sys.exit(0 if success else 1)