#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker connectivity module

This module provides robust Docker connectivity with error handling, retries,
and intelligent reconnection logic.

Features:
1. Connection pooling to reuse existing connections
2. Automatic retry with exponential backoff
3. Command output validation and cleanup
4. Health check monitoring
5. Proactive connection testing
"""

import os
import time
import json
import logging
import socket
from functools import wraps

# Import the SSH client module
from paramiko_ssh_client import ParamikoSshClient

# Import Docker output validation
from docker_output_validator import (
    clean_docker_output,
    validate_docker_info,
    extract_json_from_output,
    is_docker_running
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Connection pool to reuse SSH connections
CONNECTION_POOL = {}

def get_connection(hostname, username, port=22, password=None, key_file=None, 
                   key_data=None, key_password=None, force_new=False):
    """
    Get or create an SSH connection from the pool
    
    Args:
        hostname (str): SSH server hostname
        username (str): SSH username
        port (int): SSH port
        password (str): SSH password
        key_file (str): Path to SSH key file
        key_data (str): SSH key data as string
        key_password (str): SSH key password
        force_new (bool): Force a new connection even if one exists
        
    Returns:
        ParamikoSshClient: Connected SSH client
    """
    connection_key = f"{username}@{hostname}:{port}"
    
    # Check if we have a valid connection in the pool
    if not force_new and connection_key in CONNECTION_POOL:
        client = CONNECTION_POOL[connection_key]
        
        # Test if the connection is still valid
        try:
            test_output = client.execute_command("echo 'connection_test'", timeout=5)
            if 'connection_test' in test_output:
                logger.debug(f"Reusing existing connection for {connection_key}")
                return client
        except Exception as e:
            logger.warning(f"Existing connection for {connection_key} is stale: {str(e)}")
            # Continue to create a new connection
    
    # Create a new connection
    logger.info(f"Creating new connection for {connection_key}")
    client = ParamikoSshClient(
        hostname=hostname,
        username=username,
        port=port,
        password=password,
        key_file=key_file,
        key_data=key_data,
        key_password=key_password,
        use_clean_output=True,  # Always use clean output for Docker commands
        force_minimal_terminal=True,  # Use minimal terminal to prevent ANSI codes
        connect_timeout=15,  # Slightly longer timeout for initial connection
        command_timeout=60,  # Default command timeout
        retry_count=3,       # Default retry count
        retry_delay=2        # Default delay between retries
    )
    
    # Connect to the server
    if client.connect():
        # Store in the connection pool
        CONNECTION_POOL[connection_key] = client
        return client
    else:
        logger.error(f"Failed to connect to {connection_key}")
        return None

def with_docker_connection(max_retries=3, retry_delay=2, timeout=60):
    """
    Decorator for functions that need a Docker connection
    
    This decorator handles connection errors and retries automatically.
    
    Args:
        max_retries (int): Maximum number of retries
        retry_delay (int): Delay in seconds between retries
        timeout (int): Command timeout in seconds
        
    Returns:
        function: Decorated function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(server, *args, **kwargs):
            # Get connection parameters from server
            hostname = server.hostname
            port = server.ssh_port or 22
            username = server.username
            password = server.password
            key_file = server.key_file_path if hasattr(server, 'key_file_path') else None
            key_data = server.private_key if hasattr(server, 'private_key') else None
            
            # Track attempts
            attempts = 0
            last_error = None
            
            while attempts <= max_retries:
                if attempts > 0:
                    # Calculate exponential backoff delay
                    current_delay = retry_delay * (2 ** (attempts - 1))
                    logger.info(f"Retrying Docker operation (attempt {attempts}/{max_retries}), waiting {current_delay}s...")
                    time.sleep(current_delay)
                
                # Get a connection
                force_new = attempts > 0  # Force new connection on retry
                client = get_connection(
                    hostname=hostname,
                    username=username,
                    port=port,
                    password=password,
                    key_file=key_file,
                    key_data=key_data,
                    force_new=force_new
                )
                
                if not client:
                    attempts += 1
                    last_error = "Failed to establish SSH connection"
                    continue
                
                try:
                    # Test Docker connectivity first
                    if not test_docker_connectivity(client):
                        attempts += 1
                        last_error = "Docker daemon not accessible"
                        continue
                    
                    # Execute the actual function with the client
                    result = func(server, client, *args, **kwargs)
                    return result
                    
                except socket.timeout:
                    attempts += 1
                    last_error = "Connection timed out"
                    logger.warning(f"Docker operation timed out (attempt {attempts}/{max_retries})")
                except Exception as e:
                    attempts += 1
                    last_error = str(e)
                    logger.warning(f"Docker operation failed: {str(e)} (attempt {attempts}/{max_retries})")
            
            # All retries failed
            logger.error(f"Docker operation failed after {max_retries} retries. Last error: {last_error}")
            if hasattr(server, 'update_server_status'):
                server.update_server_status('offline', f"Failed after {max_retries} retries: {last_error}")
            return None
        
        return wrapper
    
    return decorator

def test_docker_connectivity(client):
    """
    Test if Docker is accessible via the SSH connection
    
    Args:
        client (ParamikoSshClient): SSH client
        
    Returns:
        bool: True if Docker is accessible
    """
    try:
        # Run a simple Docker command
        output = client.execute_command("docker ps", timeout=10)
        return is_docker_running(output)
    except Exception as e:
        logger.warning(f"Docker connectivity test failed: {str(e)}")
        return False

def get_docker_info(client):
    """
    Get Docker info with validation
    
    Args:
        client (ParamikoSshClient): SSH client
        
    Returns:
        dict: Docker info as dictionary or None if failed
    """
    try:
        # Run docker info with format=json if possible (newer Docker versions)
        output = client.execute_command("docker info --format '{{json .}}'", timeout=15)
        
        # Check if output is valid JSON
        try:
            info = json.loads(output.strip())
            return info
        except (json.JSONDecodeError, ValueError):
            # Try the regular docker info command
            output = client.execute_command("docker info", timeout=15)
            is_valid, message = validate_docker_info(output)
            
            if not is_valid:
                logger.warning(f"Invalid docker info output: {message}")
                return None
            
            # Parse the text output into a dictionary
            info = {}
            current_section = None
            for line in clean_docker_output(output).split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Check if this is a main section
                if ':' in line and not line.startswith(' '):
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Convert numeric values
                    if value.isdigit():
                        value = int(value)
                    
                    info[key] = value
                    current_section = key
                    
                # Sub-items in a section (indented)
                elif current_section and line.startswith(' '):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Ensure the current section is a dict
                        if not isinstance(info.get(current_section), dict):
                            info[current_section] = {}
                            
                        # Convert numeric values
                        if value.isdigit():
                            value = int(value)
                            
                        info[current_section][key] = value
            
            return info
    
    except Exception as e:
        logger.error(f"Failed to get Docker info: {str(e)}")
        return None

def run_docker_command(client, command, format_json=True, use_sudo=False, timeout=60):
    """
    Run a Docker command with proper formatting and error handling
    
    Args:
        client (ParamikoSshClient): SSH client
        command (str): Docker command to run (without 'docker' prefix)
        format_json (bool): Add --format '{{json .}}' to the command
        use_sudo (bool): Prefix the command with sudo
        timeout (int): Command timeout in seconds
        
    Returns:
        tuple: (success, result) where result is parsed JSON if successful or error message
    """
    # Construct the full command
    full_command = "docker " + command
    
    # Add JSON formatting if requested and appropriate
    if format_json and not command.endswith("--format '{{json .}}'") and 'inspect' in command:
        # Only add JSON formatting for commands that support it
        full_command += " --format '{{json .}}'"
    
    # Add sudo if requested
    if use_sudo:
        full_command = "sudo " + full_command
    
    logger.debug(f"Running Docker command: {full_command}")
    
    try:
        # Execute the command
        output = client.execute_command(full_command, timeout=timeout)
        
        # Check for common error patterns
        if "Error:" in output or "error:" in output.lower():
            error_lines = [line for line in output.split('\n') if 'error' in line.lower()]
            error_message = error_lines[0] if error_lines else "Unknown Docker error"
            return False, error_message
        
        if format_json:
            # Try to parse as JSON
            json_data, error = extract_json_from_output(output, full_command)
            if json_data:
                return True, json_data
            elif error:
                return False, error
        
        # Return as text if not JSON or JSON parsing failed
        return True, clean_docker_output(output, full_command)
        
    except Exception as e:
        logger.error(f"Error executing Docker command: {str(e)}")
        return False, str(e)

def get_docker_version(client, use_sudo=False):
    """
    Get Docker version information
    
    Args:
        client (ParamikoSshClient): SSH client
        use_sudo (bool): Whether to use sudo for the command
        
    Returns:
        dict: Version information or None if failed
    """
    success, result = run_docker_command(client, "version --format '{{json .}}'", 
                                        format_json=False, use_sudo=use_sudo)
    
    if success and isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            # Try without json formatting
            success, result = run_docker_command(client, "version", 
                                              format_json=False, use_sudo=use_sudo)
            
            if success:
                # Parse the text output
                version_info = {'Server': {}, 'Client': {}}
                current_section = None
                
                for line in result.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Check for section headers
                    if line.startswith('Client:') or line == 'Client:':
                        current_section = 'Client'
                        continue
                    elif line.startswith('Server:') or line == 'Server:':
                        current_section = 'Server'
                        continue
                    
                    # Parse key-value pairs within sections
                    if current_section and ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        version_info[current_section][key] = value
                
                return version_info
    
    return None

def check_docker_server_health(server):
    """
    Comprehensive Docker server health check
    
    Args:
        server: Docker server object with connection details
        
    Returns:
        dict: Health status information
    """
    health_info = {
        'status': 'unknown',
        'message': '',
        'details': {},
        'api_version': None,
        'engine_version': None
    }
    
    # Connect to the server
    client = get_connection(
        hostname=server.hostname,
        username=server.username,
        port=server.ssh_port or 22,
        password=server.password,
        key_data=server.private_key if hasattr(server, 'private_key') else None,
        key_file=server.key_file_path if hasattr(server, 'key_file_path') else None
    )
    
    if not client:
        health_info['status'] = 'offline'
        health_info['message'] = 'Failed to establish SSH connection'
        return health_info
    
    # Test Docker connectivity
    if not test_docker_connectivity(client):
        health_info['status'] = 'offline'
        health_info['message'] = 'Docker daemon not accessible'
        return health_info
    
    # Get Docker version
    version_info = get_docker_version(client, use_sudo=getattr(server, 'use_sudo', False))
    if not version_info:
        health_info['status'] = 'degraded'
        health_info['message'] = 'Docker is running but version info unavailable'
    else:
        # Extract API and Engine versions
        if 'Server' in version_info:
            health_info['api_version'] = version_info['Server'].get('ApiVersion')
            health_info['engine_version'] = version_info['Server'].get('Version')
        
        # Get detailed info
        docker_info = get_docker_info(client)
        if docker_info:
            health_info['details'] = docker_info
            health_info['status'] = 'online'
            health_info['message'] = 'Docker server is healthy'
        else:
            health_info['status'] = 'degraded'
            health_info['message'] = 'Docker is running but detailed info unavailable'
    
    return health_info

# Example usage
if __name__ == "__main__":
    # This is a simple test that would be run from command line
    # In practice, this module would be imported and used by Odoo models
    
    # Mock server object for testing
    class MockServer:
        def __init__(self):
            self.hostname = "example.com"
            self.username = "root"
            self.password = None
            self.private_key = "your_private_key_data"
            self.ssh_port = 22
            self.use_sudo = False
            
        def update_server_status(self, status, message):
            print(f"Server status updated: {status} - {message}")
    
    # Test the health check
    server = MockServer()
    health = check_docker_server_health(server)
    print(json.dumps(health, indent=2))