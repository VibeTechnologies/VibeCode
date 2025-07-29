"""Debug tool execution issues."""

import subprocess
import sys
import time
import threading
import re
import requests
import json
import tempfile
from pathlib import Path


def test_tool_execution_debug():
    """Debug tool execution issues."""
    
    print("🔍 Debugging tool execution...")
    
    port = 8511
    proc = subprocess.Popen([
        sys.executable, '-m', 'vibecode.cli', 'start', '--no-tunnel', '--port', str(port)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    
    server_ready = False
    uuid_path = None
    
    def read_output():
        nonlocal server_ready, uuid_path
        try:
            for line in iter(proc.stderr.readline, ''):
                print(f"SERVER: {line.strip()}")
                if 'Server is ready on port' in line:
                    server_ready = True
                if 'MCP endpoint ready at' in line:
                    uuid_match = re.search(r'/([a-f0-9]{32})', line)
                    if uuid_match:
                        uuid_path = uuid_match.group(1)
        except Exception as e:
            print(f"❌ Error reading output: {e}")
    
    output_thread = threading.Thread(target=read_output, daemon=True)
    output_thread.start()
    
    # Wait for server
    for i in range(30):
        if server_ready and uuid_path:
            break
        time.sleep(1)
    
    if not (server_ready and uuid_path):
        print("❌ Server failed to start")
        proc.terminate()
        return
    
    try:
        mcp_url = f"http://127.0.0.1:{port}/{uuid_path}"
        print(f"✅ MCP URL: {mcp_url}")
        
        # Test write tool
        print("\n🔧 Testing write tool...")
        with tempfile.TemporaryDirectory() as temp_dir:
            write_request = {
                "jsonrpc": "2.0",
                "id": "write-test",
                "method": "tools/call",
                "params": {
                    "name": "write",
                    "arguments": {
                        "file_path": f"{temp_dir}/test.txt",
                        "content": "Hello Debug Test"
                    }
                }
            }
            
            print(f"Request: {json.dumps(write_request, indent=2)}")
            
            write_response = requests.post(
                mcp_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                },
                json=write_request,
                timeout=10
            )
            
            print(f"Response Status: {write_response.status_code}")
            print(f"Response Headers: {dict(write_response.headers)}")
            print(f"Response Text: {write_response.text}")
            
            if write_response.status_code == 200:
                # Parse response
                response_text = write_response.text.strip()
                if response_text.startswith("data: "):
                    json_data = response_text.replace("data: ", "").strip()
                    write_data = json.loads(json_data)
                else:
                    write_data = write_response.json()
                
                print(f"Parsed Response: {json.dumps(write_data, indent=2)}")
                
                if "result" in write_data:
                    print("✅ Write tool succeeded")
                    
                    # Check if file was created
                    test_file = Path(temp_dir) / "test.txt"
                    if test_file.exists():
                        content = test_file.read_text()
                        print(f"✅ File created with content: {content}")
                    else:
                        print("❌ File was not created")
                else:
                    print(f"❌ No result in response: {write_data}")
            else:
                print(f"❌ Write tool failed: {write_response.status_code}")
    
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    test_tool_execution_debug()