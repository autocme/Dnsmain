#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker output validation and cleanup utility

This module helps ensure Docker command output is clean and properly formatted, 
especially when received through SSH. It handles common issues like:
1. Removing command echo lines from SSH output
2. Handling ANSI escape sequences 
3. Filtering out warnings and error messages
4. Cleaning up JSON output for parsing
"""

import re
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ANSI escape sequence pattern
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def is_json_output(output):
    """
    Check if a string is valid JSON output
    
    Args:
        output (str): Output string to check
        
    Returns:
        bool: True if the output is valid JSON, False otherwise
    """
    try:
        json.loads(output)
        return True
    except (json.JSONDecodeError, ValueError):
        return False

def extract_json_from_output(output, command_used=None):
    """
    Extract JSON data from command output, handling common issues
    
    Args:
        output (str): The command output possibly containing JSON
        command_used (str, optional): The command that was used to generate the output
        
    Returns:
        tuple: (json_object, error_message) - JSON object if found, or None with error message
    """
    if not output or not isinstance(output, str):
        return None, "Empty or invalid output"
    
    # Clean up the output
    clean_output = clean_docker_output(output, command_used)
    
    # Try to parse the cleaned output
    try:
        json_data = json.loads(clean_output)
        return json_data, None
    except (json.JSONDecodeError, ValueError) as e:
        # Failed to parse as is, try to extract JSON parts
        logger.warning(f"Failed to parse output as JSON: {str(e)}")
        
        # Look for JSON array/object patterns
        json_pattern = re.compile(r'(\[.*\]|\{.*\})', re.DOTALL)
        json_matches = json_pattern.findall(clean_output)
        
        if json_matches:
            # Try each potential JSON match
            for json_candidate in json_matches:
                try:
                    json_data = json.loads(json_candidate)
                    return json_data, None
                except (json.JSONDecodeError, ValueError):
                    continue
        
        # If we get here, no valid JSON was found
        logger.error("No valid JSON found in the output")
        return None, f"Invalid JSON format: {str(e)}"

def clean_docker_output(output, command_used=None):
    """
    Clean Docker command output to prepare for processing
    
    Args:
        output (str): Raw command output
        command_used (str, optional): The command that was used to generate the output
        
    Returns:
        str: Cleaned output
    """
    if not output:
        return ""
        
    # Remove ANSI escape sequences
    output = ANSI_ESCAPE.sub('', output)
    
    # Normalize line endings
    output = output.replace('\r\n', '\n').replace('\r', '\n')
    
    # Remove command echo if present
    if command_used:
        lines = output.split('\n')
        filtered_lines = []
        skip_next = False
        
        for line in lines:
            # Skip empty lines at the beginning
            if not filtered_lines and not line.strip():
                continue
                
            # Skip the line with the command echo
            if command_used in line:
                skip_next = True  # Sometimes the echo spans multiple lines
                continue
                
            # Skip continuation lines of the command
            if skip_next and line.startswith('+'):
                skip_next = False
                continue
                
            filtered_lines.append(line)
            
        output = '\n'.join(filtered_lines)
    
    # Remove warning lines that often precede Docker JSON output
    warning_pattern = re.compile(r'^WARNING:.*$', re.MULTILINE)
    output = warning_pattern.sub('', output)
    
    # Remove header lines like "name,id,status" that might precede table output
    header_pattern = re.compile(r'^[A-Z]+[A-Z_,]+$', re.MULTILINE)
    output = header_pattern.sub('', output)
    
    # Trim whitespace
    output = output.strip()
    
    return output

def validate_docker_info(docker_info_output):
    """
    Validate docker info command output, ensuring it's a valid response
    
    Args:
        docker_info_output (str): Output from 'docker info' command
        
    Returns:
        tuple: (is_valid, message) - validation status and message
    """
    if not docker_info_output:
        return False, "Empty docker info output"
    
    # Clean the output
    clean_output = clean_docker_output(docker_info_output, "docker info")
    
    # Check for common error patterns
    if "Cannot connect to the Docker daemon" in clean_output:
        return False, "Cannot connect to Docker daemon"
        
    if "permission denied" in clean_output.lower():
        return False, "Permission denied accessing Docker"
        
    if "Error response from daemon" in clean_output:
        # Extract the specific error message
        error_match = re.search(r'Error response from daemon: (.*)', clean_output)
        if error_match:
            return False, f"Docker daemon error: {error_match.group(1)}"
        else:
            return False, "Unknown Docker daemon error"
    
    # Check for key content that should be in a valid docker info output
    required_sections = [
        "Containers:", 
        "Images:", 
        "Server Version:",
        "Storage Driver:"
    ]
    
    for section in required_sections:
        if section not in clean_output:
            return False, f"Missing expected section: {section}"
    
    return True, "Valid docker info output"

def extract_api_version(version_output):
    """
    Extract Docker API version from docker version command output
    
    Args:
        version_output (str): Output from 'docker version' command
        
    Returns:
        str: API version string or None if not found
    """
    clean_output = clean_docker_output(version_output, "docker version")
    
    # Try JSON format first
    try:
        data = json.loads(clean_output)
        if "Server" in data and "ApiVersion" in data["Server"]:
            return data["Server"]["ApiVersion"]
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    
    # Try text format with regex
    api_pattern = re.compile(r'API version:\s+([0-9.]+)', re.IGNORECASE)
    match = api_pattern.search(clean_output)
    
    if match:
        return match.group(1)
    
    return None

def is_docker_running(docker_ps_output):
    """
    Check if Docker is running based on a simple docker ps command
    
    Args:
        docker_ps_output (str): Output from 'docker ps' command
        
    Returns:
        bool: True if Docker appears to be running
    """
    clean_output = clean_docker_output(docker_ps_output, "docker ps")
    
    # Error patterns indicating Docker is not running
    error_patterns = [
        "Cannot connect to the Docker daemon",
        "Error response from daemon",
        "permission denied",
        "docker daemon is not running"
    ]
    
    for pattern in error_patterns:
        if pattern.lower() in clean_output.lower():
            return False
    
    # Success patterns indicating Docker is running
    # Even if there are no containers, the command would succeed with headers
    success_patterns = [
        "CONTAINER ID",
        "NAMES",
        "IMAGE",
        "STATUS"
    ]
    
    for pattern in success_patterns:
        if pattern in clean_output:
            return True
    
    # If we can't definitively tell, assume it's not running
    return False

# Test the module if run directly
if __name__ == "__main__":
    # Simple test with sample output
    sample_output = """
    $ docker info
    WARNING: No swap limit support
    Containers: 13
     Running: 5
     Paused: 0
     Stopped: 8
    Images: 17
    Server Version: 20.10.7
    Storage Driver: overlay2
     Backing Filesystem: extfs
    Logging Driver: json-file
    Cgroup Driver: cgroupfs
    """
    
    clean = clean_docker_output(sample_output, "docker info")
    print("Cleaned output:")
    print(clean)
    
    is_valid, message = validate_docker_info(sample_output)
    print(f"Valid docker info: {is_valid}, Message: {message}")