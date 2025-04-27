#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker API v1.49 Feature Test Script

This script tests the Docker API v1.49 specific features including:
1. BuildKit build progress events
2. Registry search enhancements
3. Multi-platform images in resource listings
4. Enhanced image buildinfo

Requires a Docker server with API v1.49 support (Docker 25.0.x or newer)
"""

import os
import sys
import json
import argparse
import logging
from paramiko_ssh_client import ParamikoSshClient
from docker_api_1_49_support import DockerApi149Support
from enhanced_docker_connectivity import (
    get_connection,
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
        self.detected_sudo_required = None
        
    def update_server_status(self, status, message):
        print(f"Server status updated: {status} - {message}")

def check_api_version(client, use_sudo):
    """Check if the Docker server supports API v1.49"""
    print("\n===== Checking Docker API Version =====")
    
    version_info = get_docker_version(client, use_sudo=use_sudo)
    if not version_info:
        print("❌ Failed to get Docker version information")
        return None
    
    # Extract API version
    api_version = None
    if 'Server' in version_info:
        if 'ApiVersion' in version_info['Server']:
            api_version = version_info['Server']['ApiVersion']
        elif 'Engine' in version_info['Server'] and 'ApiVersion' in version_info['Server']['Engine']:
            api_version = version_info['Server']['Engine']['ApiVersion']
    
    if not api_version:
        print("❌ Could not determine Docker API version")
        return None
    
    print(f"✅ Docker API Version: {api_version}")
    
    # Check API v1.49 support
    is_supported = DockerApi149Support.is_api_149_supported(api_version)
    if is_supported:
        print("✅ API v1.49 features are supported")
    else:
        print("❌ API v1.49 features are NOT supported")
    
    return api_version if is_supported else None

def test_buildkit_progress(client, use_sudo):
    """Test BuildKit build progress events"""
    print("\n===== Testing BuildKit Build Progress =====")
    
    # Create a simple Dockerfile
    dockerfile = """FROM alpine:latest
RUN echo "Hello, world!" > /hello.txt
RUN apk add --no-cache curl
RUN sleep 2
CMD ["cat", "/hello.txt"]
"""
    
    # Create a temporary directory and Dockerfile
    create_dir_cmd = "mkdir -p /tmp/docker_test"
    client.execute_command(create_dir_cmd)
    
    create_file_cmd = f"cat > /tmp/docker_test/Dockerfile << 'EOF'\n{dockerfile}\nEOF"
    client.execute_command(create_file_cmd)
    
    # Run the BuildKit build with progress
    build_cmd = DockerApi149Support.get_buildkit_progress_command(
        "api149test:latest", 
        "/tmp/docker_test",
        build_args={"VERSION": "latest"}
    )
    
    if use_sudo:
        build_cmd = f"sudo {build_cmd}"
    
    print("Running build with progress tracking...")
    output = client.execute_command(build_cmd, timeout=120)
    
    # Parse the progress output
    progress_data = DockerApi149Support.parse_buildkit_progress(output)
    
    if not progress_data.get('stages'):
        print("❌ Could not parse BuildKit progress data")
        print("Output sample:", output[:200] + "...")
        return False
    
    print("✅ Successfully captured BuildKit progress events")
    print(f"  Stages: {len(progress_data['stages'])}")
    for stage, data in progress_data['stages'].items():
        print(f"  - {stage}: {data['status']} ({len(data['steps'])} steps)")
    
    return True

def test_registry_search(client, use_sudo):
    """Test enhanced registry search"""
    print("\n===== Testing Enhanced Registry Search =====")
    
    # Test search with filters
    search_results = DockerApi149Support.enhanced_registry_search(
        client,
        "ubuntu",
        filters={"is-official": "true"},
        limit=5,
        use_sudo=use_sudo
    )
    
    if not search_results:
        print("❌ Registry search returned no results")
        return False
    
    print(f"✅ Registry search returned {len(search_results)} results")
    for i, result in enumerate(search_results[:3], 1):
        print(f"  {i}. {result.get('Name', 'Unknown')} - Stars: {result.get('StarCount', 0)}")
    
    return True

def test_multiplatform_images(client, use_sudo):
    """Test multi-platform image listing"""
    print("\n===== Testing Multi-Platform Image Listing =====")
    
    # Pull a multi-platform image if needed
    pull_cmd = "docker pull --platform linux/amd64 ubuntu:latest"
    if use_sudo:
        pull_cmd = f"sudo {pull_cmd}"
    
    print("Pulling a test image (this may take a moment)...")
    client.execute_command(pull_cmd, timeout=120)
    
    # Get multi-platform images
    multiplatform_images = DockerApi149Support.get_multiplatform_images(client, use_sudo=use_sudo)
    
    if not multiplatform_images:
        print("⚠️ No multi-platform images found")
        print("This is OK if the server doesn't have any multi-platform images")
        return True
    
    print(f"✅ Found {len(multiplatform_images)} multi-platform images")
    for i, image in enumerate(multiplatform_images[:3], 1):
        print(f"  {i}. {image.get('Repository', 'Unknown')}:{image.get('Tag', 'Unknown')}")
        print(f"     Platform: {image.get('Platform', 'Unknown')}")
    
    return True

def test_enhanced_build_info(client, use_sudo):
    """Test enhanced image build info"""
    print("\n===== Testing Enhanced Build Info =====")
    
    # Get the first available image
    cmd = "docker images --format '{{json .}}' | head -1"
    if use_sudo:
        cmd = f"sudo {cmd}"
    
    output = client.execute_command(cmd)
    try:
        image_data = json.loads(output.strip())
        image_id = image_data.get('ID', None)
    except json.JSONDecodeError:
        image_id = None
    
    if not image_id:
        print("❌ No images available to test build info")
        return False
    
    # Get build info
    build_info = DockerApi149Support.get_build_info(client, image_id, use_sudo=use_sudo)
    
    if not build_info:
        print("❌ Could not get build info")
        return False
    
    print(f"✅ Successfully retrieved build info for image {image_id}")
    print(f"  Architecture: {build_info.get('Architecture', 'Unknown')}")
    print(f"  OS: {build_info.get('Os', 'Unknown')}")
    print(f"  Size: {build_info.get('Size', 0)} bytes")
    
    # Check for build info details
    if 'BuildInfo' in build_info and build_info['BuildInfo']:
        print("  Build Info Details Available:")
        for key, value in build_info['BuildInfo'].items():
            print(f"    - {key}: {type(value).__name__}")
    else:
        print("  No detailed build info available (this is normal for base images)")
    
    return True

def test_api_version_html(client, use_sudo, api_version):
    """Test API version HTML generation"""
    print("\n===== Testing API Version HTML Generation =====")
    
    html = DockerApi149Support.generate_api_version_html(api_version)
    
    if not html:
        print("❌ Failed to generate API version HTML")
        return False
    
    print("✅ Successfully generated API version HTML")
    print("HTML sample (first 200 chars):")
    print(html[:200] + "...")
    
    # Create a sample HTML file
    html_file = "/tmp/docker_api_features.html"
    create_file_cmd = f"cat > {html_file} << 'EOF'\n{html}\nEOF"
    client.execute_command(create_file_cmd)
    
    print(f"HTML file created at {html_file}")
    return True

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Test Docker API v1.49 features')
    
    # Connection parameters
    parser.add_argument('--hostname', required=True, help='SSH hostname')
    parser.add_argument('--port', type=int, default=22, help='SSH port')
    parser.add_argument('--username', required=True, help='SSH username')
    parser.add_argument('--password', help='SSH password')
    parser.add_argument('--key-file', help='SSH private key file')
    parser.add_argument('--sudo', action='store_true', help='Use sudo for Docker commands')
    
    # Test selection
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--buildkit', action='store_true', help='Test BuildKit progress')
    parser.add_argument('--search', action='store_true', help='Test registry search')
    parser.add_argument('--multiplatform', action='store_true', help='Test multi-platform images')
    parser.add_argument('--buildinfo', action='store_true', help='Test enhanced build info')
    parser.add_argument('--html', action='store_true', help='Test API HTML generation')
    
    args = parser.parse_args()
    
    # If no specific tests selected, run them all
    if not (args.all or args.buildkit or args.search or args.multiplatform or args.buildinfo or args.html):
        args.all = True
    
    # Create a test server object
    server = TestServer(
        hostname=args.hostname,
        username=args.username,
        password=args.password,
        key_file=args.key_file,
        ssh_port=args.port,
        use_sudo=args.sudo
    )
    
    # Connect to the server
    client = get_connection(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port,
        password=server.password,
        key_file=server.key_file_path
    )
    
    if not client:
        print("Failed to connect to the server")
        return 1
    
    # Check API version
    api_version = check_api_version(client, args.sudo)
    if not api_version:
        print("This server does not support Docker API v1.49")
        print("Tests will be skipped")
        return 1
    
    tests_passed = 0
    tests_failed = 0
    
    # Run selected tests
    if args.all or args.buildkit:
        if test_buildkit_progress(client, args.sudo):
            tests_passed += 1
        else:
            tests_failed += 1
    
    if args.all or args.search:
        if test_registry_search(client, args.sudo):
            tests_passed += 1
        else:
            tests_failed += 1
    
    if args.all or args.multiplatform:
        if test_multiplatform_images(client, args.sudo):
            tests_passed += 1
        else:
            tests_failed += 1
    
    if args.all or args.buildinfo:
        if test_enhanced_build_info(client, args.sudo):
            tests_passed += 1
        else:
            tests_failed += 1
    
    if args.all or args.html:
        if test_api_version_html(client, args.sudo, api_version):
            tests_passed += 1
        else:
            tests_failed += 1
    
    # Print summary
    print("\n===== Test Summary =====")
    print(f"✅ Tests passed: {tests_passed}")
    print(f"❌ Tests failed: {tests_failed}")
    
    return 0 if tests_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())