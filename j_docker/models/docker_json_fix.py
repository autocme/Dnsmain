#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import logging

_logger = logging.getLogger(__name__)

def clean_docker_output(output):
    """Clean SSH output from Docker commands
    
    Args:
        output (str): Raw SSH output
        
    Returns:
        str: Cleaned output
    """
    if not output:
        return ""
    
    # Remove terminal color codes
    output = re.sub(r'\x1B\[[0-9;]*[mK]', '', output)
    
    # Remove common patterns that appear in SSH output
    patterns = [
        # Commands and line continuation prompts
        r'^.*\$ .*docker.*$',  # Command being echoed
        r'^\> .*$',            # Line continuation in bash
        
        # Shell environment text
        r'^.*Last login:.*$',
        r'^.*Welcome to.*$',
        r'^.*Linux.*$',
        
        # Common shell error messages
        r'^bash: .*$',
        r'^-bash: .*$',
        r'^sh: .*$',
        
        # Sudo patterns 
        r'^\[sudo\].*$',
        r'^.*password for.*:.*$',
    ]
    
    # Apply patterns line by line
    lines = output.split('\n')
    cleaned_lines = []
    
    for line in lines:
        skip = False
        for pattern in patterns:
            if re.match(pattern, line):
                skip = True
                break
        
        if not skip:
            cleaned_lines.append(line)
            
    return '\n'.join(cleaned_lines)

def fix_json_command_output(output):
    """Fix common issues with JSON output from SSH commands
    
    Args:
        output (str): Raw SSH JSON output
        
    Returns:
        str: Fixed JSON string ready for parsing
    """
    if not output:
        return "{}"
    
    # First clean the output
    output = clean_docker_output(output)
    
    # Remove any tracing or debug output before the JSON data
    # This matches everything before the first '{' or '['
    match = re.search(r'[\[\{]', output)
    if match:
        start_index = match.start()
        output = output[start_index:]
    
    # Remove any trailing output after the JSON data
    # Find the position of the last '}' or ']'
    match = re.search(r'[\]\}][^\]\}]*$', output)
    if match:
        # Keep the last '}' or ']' but remove anything after it
        end_index = match.start() + 1
        output = output[:end_index]
    
    # Handle special case where we get multiple JSON objects
    # For example, docker ps returns one JSON object per line
    if output.strip() and not (output.strip().startswith('{') or output.strip().startswith('[')):
        # Return as-is, will be processed line by line
        return output
    
    # Fix missing quotes around keys
    output = re.sub(r'(\s*)(\w+)(\s*):(\s*)', r'\1"\2"\3:\4', output)
    
    # Fix trailing commas in arrays and objects
    output = re.sub(r',(\s*[\}\]])', r'\1', output)
    
    # Fix control characters
    output = re.sub(r'[\x00-\x1F\x7F]', '', output)
    
    # Validate the JSON
    try:
        json.loads(output)
        return output
    except json.JSONDecodeError as e:
        _logger.error(f"Failed to parse JSON: {e}")
        _logger.debug(f"Problem JSON: {output}")
        # Return an empty object for invalid JSON
        return "{}"