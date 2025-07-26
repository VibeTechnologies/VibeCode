#!/usr/bin/env python3
"""
Query available tools from VibeCode MCP server
"""

import requests
import json
import sys

def query_tools(host="localhost", port=8300):
    """Query available tools from MCP server"""
    url = f"http://{host}:{port}/"
    
    # MCP protocol request for tools/list
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        print(f"🔍 Querying tools from {url}...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        
        if "result" in result and "tools" in result["result"]:
            tools = result["result"]["tools"]
            print(f"\n✅ Found {len(tools)} available tools:\n")
            
            for i, tool in enumerate(tools, 1):
                name = tool.get("name", "Unknown")
                description = tool.get("description", "No description")
                
                print(f"{i:2d}. {name}")
                print(f"    📋 {description}")
                
                # Show input schema if available
                if "inputSchema" in tool:
                    schema = tool["inputSchema"]
                    if "properties" in schema:
                        props = list(schema["properties"].keys())
                        required = schema.get("required", [])
                        print(f"    📥 Parameters: {', '.join(props)}")
                        if required:
                            print(f"    ⚠️  Required: {', '.join(required)}")
                print()
            
            # Show special tools
            special_tools = [t for t in tools if t["name"] in ["claude_code", "agent"]]
            if special_tools:
                print("🌟 **Special Integration Tools:**")
                for tool in special_tools:
                    print(f"   • {tool['name']}: {tool.get('description', 'No description')}")
                print()
                
        else:
            print("❌ Unexpected response format:")
            print(json.dumps(result, indent=2))
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to {url}")
        print("💡 Make sure VibeCode server is running:")
        print("   vibecode start --no-tunnel --port 8300")
        sys.exit(1)
        
    except requests.exceptions.Timeout:
        print(f"⏱️  Request timed out to {url}")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error querying tools: {e}")
        sys.exit(1)

def query_server_info(host="localhost", port=8300):
    """Query server information"""
    url = f"http://{host}:{port}/"
    
    payload = {
        "jsonrpc": "2.0", 
        "id": 2,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "tool-query-client",
                "version": "1.0.0"
            }
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if "result" in result:
            server_info = result["result"]
            print("🖥️  **Server Information:**")
            print(f"   • Protocol Version: {server_info.get('protocolVersion', 'Unknown')}")
            if "serverInfo" in server_info:
                info = server_info["serverInfo"]
                print(f"   • Server: {info.get('name', 'Unknown')} v{info.get('version', 'Unknown')}")
            print()
            
    except Exception as e:
        print(f"⚠️  Could not get server info: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Query VibeCode MCP server tools")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    parser.add_argument("--port", type=int, default=8300, help="Server port (default: 8300)")
    parser.add_argument("--info", action="store_true", help="Also show server information")
    
    args = parser.parse_args()
    
    if args.info:
        query_server_info(args.host, args.port)
    
    query_tools(args.host, args.port)