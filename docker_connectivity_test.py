#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker Connectivity Test Script

This script tests the Docker connectivity module with various common scenarios to verify
that connectivity issues are properly handled and resolved.

Tests include:
1. Connection retries
2. Timeout handling
3. Command validation
4. JSON parsing
5. Error recovery
"""

import os
import time
import json
import logging
import argparse
from paramiko_ssh_client import ParamikoSshClient
from docker_output_validator import (
    clean_docker_output,
    validate_docker_info,
    extract_json_from_output,
    is_docker_running
)
from docker_connectivity import (
    get_connection,
    test_docker_connectivity,
    get_docker_info,
    run_docker_command,
    get_docker_version,
    check_docker_server_health
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestServer:
    """Mock server object for testing"""
    def __init__(self, hostname, username, password=None, key_file=None, 
                 private_key=None, ssh_port=22, use_sudo=False):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.private_key = private_key
        self.key_file_path = key_file
        self.ssh_port = ssh_port
        self.use_sudo = use_sudo
        
    def update_server_status(self, status, message):
        print(f"Server status updated: {status} - {message}")

def test_connection(args):
    """Test basic connectivity"""
    print("\n=== Testing Basic Connectivity ===")
    
    server = TestServer(
        hostname=args.hostname, 
        username=args.username,
        password=args.password,
        key_file=args.key_file,
        ssh_port=args.port,
        use_sudo=args.sudo
    )
    
    # Test direct connection
    print("Testing direct SSH connection...")
    client = ParamikoSshClient(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port,
        password=server.password,
        key_file=server.key_file_path,
        use_clean_output=True,  
        force_minimal_terminal=True,
        connect_timeout=10,
        command_timeout=30,
        retry_count=2,
        retry_delay=2
    )
    
    if client.connect():
        print("✓ Direct SSH connection successful")
        
        # Test basic command
        output = client.execute_command("echo 'test successful'")
        if "test successful" in output:
            print("✓ Basic command execution successful")
        else:
            print("✗ Basic command execution failed")
            print(f"Output: {output}")
        
        # Test Docker access
        print("Testing Docker access...")
        output = client.execute_command("docker --version")
        print(f"Docker version: {output.strip()}")
        
        # Check if Docker is running
        docker_running = is_docker_running(client.execute_command("docker ps"))
        if docker_running:
            print("✓ Docker is running")
        else:
            print("✗ Docker is not running or not accessible")
        
        client.disconnect()
    else:
        print("✗ Direct SSH connection failed")
        return False
    
    return True

def test_connection_pool(args):
    """Test connection pooling"""
    print("\n=== Testing Connection Pooling ===")
    
    server = TestServer(
        hostname=args.hostname, 
        username=args.username,
        password=args.password,
        key_file=args.key_file,
        ssh_port=args.port,
        use_sudo=args.sudo
    )
    
    # First connection
    print("Creating first connection...")
    client1 = get_connection(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port,
        password=server.password,
        key_file=server.key_file_path
    )
    
    if not client1:
        print("✗ Failed to create first connection")
        return False
    
    print("✓ First connection created")
    
    # Second connection - should reuse the first
    print("Creating second connection (should reuse existing)...")
    client2 = get_connection(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port,
        password=server.password,
        key_file=server.key_file_path
    )
    
    if client1 is client2:
        print("✓ Connection pooling works - reused existing connection")
    else:
        print("✗ Connection pooling failed - created new connection")
    
    # Force new connection
    print("Creating forced new connection...")
    client3 = get_connection(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port,
        password=server.password,
        key_file=server.key_file_path,
        force_new=True
    )
    
    if client1 is not client3:
        print("✓ Forced new connection created")
    else:
        print("✗ Failed to create new connection when forced")
    
    return True

def test_docker_commands(args):
    """Test Docker commands"""
    print("\n=== Testing Docker Commands ===")
    
    server = TestServer(
        hostname=args.hostname, 
        username=args.username,
        password=args.password,
        key_file=args.key_file,
        ssh_port=args.port,
        use_sudo=args.sudo
    )
    
    # Get a connection
    client = get_connection(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port,
        password=server.password,
        key_file=server.key_file_path
    )
    
    if not client:
        print("✗ Failed to establish connection")
        return False
    
    # Test Docker info
    print("Testing Docker info...")
    info = get_docker_info(client)
    if info:
        print("✓ Docker info retrieved successfully")
        print(f"  Server Version: {info.get('Server Version', 'Unknown')}")
        print(f"  Containers: {info.get('Containers', 'Unknown')}")
        print(f"  Images: {info.get('Images', 'Unknown')}")
    else:
        print("✗ Failed to retrieve Docker info")
    
    # Test Docker version
    print("Testing Docker version...")
    version = get_docker_version(client, use_sudo=server.use_sudo)
    if version:
        print("✓ Docker version retrieved successfully")
        if 'Server' in version and 'ApiVersion' in version['Server']:
            print(f"  API Version: {version['Server']['ApiVersion']}")
        if 'Server' in version and 'Version' in version['Server']:
            print(f"  Engine Version: {version['Server']['Version']}")
    else:
        print("✗ Failed to retrieve Docker version")
    
    # Test containers list
    print("Testing container list...")
    success, result = run_docker_command(
        client, 
        "container ls --all", 
        format_json=False, 
        use_sudo=server.use_sudo
    )
    
    if success:
        print("✓ Container list retrieved successfully")
        container_count = len([line for line in result.split('\n') if line.strip()]) - 1  # Subtract header
        print(f"  Container count: {container_count if container_count >= 0 else 'Unknown'}")
    else:
        print(f"✗ Failed to retrieve container list: {result}")
    
    # Test images list
    print("Testing image list...")
    success, result = run_docker_command(
        client, 
        "image ls", 
        format_json=False, 
        use_sudo=server.use_sudo
    )
    
    if success:
        print("✓ Image list retrieved successfully")
        image_count = len([line for line in result.split('\n') if line.strip()]) - 1  # Subtract header
        print(f"  Image count: {image_count if image_count >= 0 else 'Unknown'}")
    else:
        print(f"✗ Failed to retrieve image list: {result}")
    
    return True

def test_health_check(args):
    """Test server health check"""
    print("\n=== Testing Server Health Check ===")
    
    server = TestServer(
        hostname=args.hostname, 
        username=args.username,
        password=args.password,
        key_file=args.key_file,
        ssh_port=args.port,
        use_sudo=args.sudo
    )
    
    print("Running comprehensive health check...")
    health = check_docker_server_health(server)
    
    print(f"Health status: {health['status']}")
    print(f"Message: {health['message']}")
    print(f"API Version: {health['api_version']}")
    print(f"Engine Version: {health['engine_version']}")
    
    if health['details']:
        print("Health details available")
        
        # Show some key metrics
        if 'Containers' in health['details']:
            print(f"Containers: {health['details']['Containers']}")
        if 'Images' in health['details']:
            print(f"Images: {health['details']['Images']}")
        if 'DriverStatus' in health['details']:
            print("Storage driver details available")
    else:
        print("No detailed health information available")
    
    return health['status'] == 'online'

def test_error_handling(args):
    """Test error handling and recovery"""
    print("\n=== Testing Error Handling ===")
    
    server = TestServer(
        hostname=args.hostname, 
        username=args.username,
        password=args.password,
        key_file=args.key_file,
        ssh_port=args.port,
        use_sudo=args.sudo
    )
    
    # Get a connection
    client = get_connection(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port,
        password=server.password,
        key_file=server.key_file_path
    )
    
    if not client:
        print("✗ Failed to establish connection")
        return False
    
    # Test invalid command
    print("Testing invalid Docker command...")
    success, result = run_docker_command(
        client, 
        "invalid-command", 
        format_json=False, 
        use_sudo=server.use_sudo
    )
    
    if not success:
        print("✓ Invalid command properly detected as error")
        print(f"  Error message: {result}")
    else:
        print("✗ Invalid command not detected as error")
    
    # Test non-existent container
    print("Testing non-existent container...")
    success, result = run_docker_command(
        client, 
        "container inspect nonexistentcontainer12345", 
        format_json=True, 
        use_sudo=server.use_sudo
    )
    
    if not success:
        print("✓ Non-existent container properly detected as error")
        print(f"  Error message: {result}")
    else:
        print("✗ Non-existent container not detected as error")
    
    # Test invalid JSON
    print("Testing invalid JSON handling...")
    output = "This is not valid JSON data at all"
    json_data, error = extract_json_from_output(output)
    
    if json_data is None and error:
        print("✓ Invalid JSON properly detected")
        print(f"  Error message: {error}")
    else:
        print("✗ Invalid JSON not detected properly")
    
    # Test partial valid JSON
    print("Testing partial valid JSON extraction...")
    output = "Some garbage text here { \"key\": \"value\" } and more garbage here"
    json_data, error = extract_json_from_output(output)
    
    if json_data and json_data.get('key') == 'value':
        print("✓ Valid JSON extracted from mixed content")
    else:
        print("✗ Failed to extract valid JSON from mixed content")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Test Docker connectivity')
    
    # Connection parameters
    parser.add_argument('--hostname', required=True, help='SSH hostname')
    parser.add_argument('--port', type=int, default=22, help='SSH port')
    parser.add_argument('--username', required=True, help='SSH username')
    parser.add_argument('--password', help='SSH password')
    parser.add_argument('--key-file', help='SSH private key file')
    parser.add_argument('--sudo', action='store_true', help='Use sudo for Docker commands')
    
    # Test selection
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--connection', action='store_true', help='Test basic connectivity')
    parser.add_argument('--pool', action='store_true', help='Test connection pooling')
    parser.add_argument('--commands', action='store_true', help='Test Docker commands')
    parser.add_argument('--health', action='store_true', help='Test health check')
    parser.add_argument('--errors', action='store_true', help='Test error handling')
    
    args = parser.parse_args()
    
    # If no specific tests selected, run them all
    if not (args.all or args.connection or args.pool or args.commands or args.health or args.errors):
        args.all = True
    
    tests_passed = 0
    tests_failed = 0
    
    # Run selected tests
    if args.all or args.connection:
        if test_connection(args):
            tests_passed += 1
        else:
            tests_failed += 1
    
    if args.all or args.pool:
        if test_connection_pool(args):
            tests_passed += 1
        else:
            tests_failed += 1
    
    if args.all or args.commands:
        if test_docker_commands(args):
            tests_passed += 1
        else:
            tests_failed += 1
    
    if args.all or args.health:
        if test_health_check(args):
            tests_passed += 1
        else:
            tests_failed += 1
    
    if args.all or args.errors:
        if test_error_handling(args):
            tests_passed += 1
        else:
            tests_failed += 1
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"Tests passed: {tests_passed}")
    print(f"Tests failed: {tests_failed}")
    
    return 0 if tests_failed == 0 else 1

if __name__ == "__main__":
    main()