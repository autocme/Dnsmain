#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker Permission Handler

This module detects and resolves common Docker permission issues by:
1. Automatically trying sudo when permission denied
2. Suggesting user group adjustments
3. Providing clear error messages with solutions
4. Supporting socket path customization
"""

import re
import logging
import json
from typing import Tuple, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Permission error patterns
PERMISSION_DENIED_PATTERNS = [
    r"permission denied.*docker.sock",
    r"connect: permission denied",
    r"Cannot connect to the Docker daemon.*permission",
    r"dial unix.*: connect: permission denied",
    r"Got permission denied.*docker.sock"
]

def detect_permission_error(output: str) -> bool:
    """
    Detect if Docker output indicates a permission error
    
    Args:
        output (str): Command output string
        
    Returns:
        bool: True if a permission error is detected
    """
    if not output:
        return False
        
    for pattern in PERMISSION_DENIED_PATTERNS:
        if re.search(pattern, output, re.IGNORECASE):
            return True
            
    return False

def handle_permission_issue(ssh_client, command: str, output: str) -> Tuple[bool, Any]:
    """
    Handle Docker permission issues by trying sudo and providing guidance
    
    Args:
        ssh_client: The SSH client instance
        command (str): The original Docker command
        output (str): The error output from the command
        
    Returns:
        tuple: (success, result) - Success flag and result or error message
    """
    if not detect_permission_error(output):
        # Not a permission error, return original output
        return False, output
    
    logger.info("Detected Docker permission issue, attempting with sudo")
    
    # Try with sudo
    sudo_command = f"sudo {command}"
    sudo_output = ssh_client.execute_command(sudo_command)
    
    # Check if sudo worked
    if not detect_permission_error(sudo_output):
        logger.info("Command succeeded with sudo")
        
        # Try to parse as JSON if the output appears to be JSON
        if sudo_output.strip().startswith('{') or sudo_output.strip().startswith('['):
            try:
                parsed_output = json.loads(sudo_output.strip())
                return True, parsed_output
            except json.JSONDecodeError:
                pass
        
        return True, sudo_output
    
    # If sudo also failed, provide guidance
    logger.warning("Command failed even with sudo")
    error_info = {
        "error": "Docker permission denied",
        "message": "Unable to access Docker daemon, even with sudo",
        "solutions": [
            "1. Add user to the docker group: sudo usermod -aG docker $USER",
            "2. Use a user with Docker permissions",
            "3. Configure Docker to listen on TCP socket with proper authentication",
            "4. Restart Docker service: sudo systemctl restart docker"
        ],
        "original_error": output
    }
    
    return False, error_info

def suggest_docker_permission_fix(username: str) -> str:
    """
    Generate shell commands to fix Docker permissions
    
    Args:
        username (str): Username to add to Docker group
        
    Returns:
        str: Shell commands to fix permissions
    """
    commands = f"""
# Fix Docker permissions for user {username}
sudo usermod -aG docker {username}

# Restart Docker service
sudo systemctl restart docker

# Verify permissions
id {username}
groups {username}

# Note: You'll need to log out and back in for group changes to take effect
# Or run this command to apply changes to current session:
newgrp docker
"""
    return commands

def check_docker_socket_permissions(ssh_client) -> Dict[str, Any]:
    """
    Check Docker socket permissions and ownership
    
    Args:
        ssh_client: The SSH client instance
        
    Returns:
        dict: Information about the Docker socket
    """
    # Check the socket file permissions
    ls_output = ssh_client.execute_command("ls -l /var/run/docker.sock")
    
    # Check the docker group
    group_output = ssh_client.execute_command("getent group docker")
    
    # Check current user groups
    user_output = ssh_client.execute_command("id")
    
    # Parse the information
    socket_info = {
        "socket_path": "/var/run/docker.sock",
        "socket_details": ls_output.strip(),
        "docker_group": group_output.strip(),
        "user_info": user_output.strip(),
        "is_in_docker_group": "docker" in user_output
    }
    
    return socket_info

def test_docker_command_permissions(ssh_client, use_sudo: bool = False) -> Dict[str, Any]:
    """
    Test various Docker commands to determine permission status
    
    Args:
        ssh_client: The SSH client instance
        use_sudo (bool): Whether to test with sudo
        
    Returns:
        dict: Test results for different Docker commands
    """
    test_commands = {
        "version": "docker version",
        "info": "docker info",
        "ps": "docker ps",
        "images": "docker images",
        "networks": "docker network ls",
        "volumes": "docker volume ls"
    }
    
    results = {}
    
    for name, cmd in test_commands.items():
        # Try without sudo first
        no_sudo_output = ssh_client.execute_command(cmd)
        no_sudo_permission_error = detect_permission_error(no_sudo_output)
        
        # Try with sudo if requested or if direct command failed
        sudo_output = None
        sudo_permission_error = None
        if use_sudo or no_sudo_permission_error:
            sudo_output = ssh_client.execute_command(f"sudo {cmd}")
            sudo_permission_error = detect_permission_error(sudo_output)
        
        results[name] = {
            "direct_access": not no_sudo_permission_error,
            "sudo_access": not sudo_permission_error if sudo_output else None,
            "output": no_sudo_output if not no_sudo_permission_error else (sudo_output if not sudo_permission_error else None)
        }
    
    # Summarize the results
    summary = {
        "direct_access_allowed": all(r["direct_access"] for r in results.values()),
        "sudo_access_allowed": all(r["sudo_access"] for r in results.values() if r["sudo_access"] is not None),
        "requires_sudo": not all(r["direct_access"] for r in results.values()) and all(r["sudo_access"] for r in results.values() if r["sudo_access"] is not None),
        "no_access": not all(r["direct_access"] for r in results.values()) and not all(r["sudo_access"] for r in results.values() if r["sudo_access"] is not None),
        "command_results": results
    }
    
    return summary

def fix_docker_permissions(ssh_client, username: str) -> Tuple[bool, str]:
    """
    Attempt to fix Docker permissions by adding user to docker group
    
    Args:
        ssh_client: The SSH client instance
        username (str): Username to add to Docker group
        
    Returns:
        tuple: (success, message) - Success flag and result message
    """
    # Check if user is already in docker group
    id_output = ssh_client.execute_command(f"id {username}")
    if "docker" in id_output:
        return True, f"User {username} is already in the docker group. Try logging out and back in."
    
    # Add user to docker group
    cmd_output = ssh_client.execute_command(f"sudo usermod -aG docker {username}")
    if cmd_output and "error" in cmd_output.lower():
        return False, f"Failed to add user to docker group: {cmd_output}"
    
    # Restart Docker service
    restart_output = ssh_client.execute_command("sudo systemctl restart docker")
    if restart_output and "error" in restart_output.lower():
        return False, f"Failed to restart Docker service: {restart_output}"
    
    # Verify group membership
    verify_output = ssh_client.execute_command(f"id {username}")
    if "docker" in verify_output:
        return True, f"Successfully added user {username} to docker group. Log out and back in for changes to take effect."
    else:
        return False, f"User was not added to docker group. Manual intervention required."

# Example usage
if __name__ == "__main__":
    # This would be used in actual code like:
    """
    from paramiko_ssh_client import ParamikoSshClient
    from docker_permission_handler import detect_permission_error, handle_permission_issue
    
    client = ParamikoSshClient(hostname="example.com", username="user", password="pass")
    if client.connect():
        output = client.execute_command("docker ps")
        
        if detect_permission_error(output):
            success, result = handle_permission_issue(client, "docker ps", output)
            if success:
                print("Command succeeded with sudo")
                print(result)
            else:
                print("Command failed, permission issue detected")
                print(result["solutions"])
    """
    print("Docker permission handler module loaded")