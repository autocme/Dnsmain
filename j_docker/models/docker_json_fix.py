#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import logging

_logger = logging.getLogger(__name__)

def fix_json_command_output(output, command=None):
    """
    Fix JSON command output by removing command echo and other non-JSON content
    
    Args:
        output (str): Raw command output
        command (str, optional): Command that was executed
        
    Returns:
        str: Cleaned JSON string
    """
    if not output:
        return ""
    
    # Remove leading whitespace
    cleaned = output.strip()
    
    # Handle command echo in the output
    if command:
        # Remove the command if it's at the start of the output
        if cleaned.startswith(command):
            cleaned = cleaned[len(command):].strip()
        
        # Look for common patterns of command echo
        cmd_patterns = [
            r'^.*?\$ ' + re.escape(command),  # bash prompt with $
            r'^.*?# ' + re.escape(command),   # root prompt with #
            r'^.*?> ' + re.escape(command),   # other prompts with >
            r'^.*?<.*?> ' + re.escape(command),  # custom prompt with <>
            r'^<?(TERM=dumb && )?' + re.escape(command)  # TERM environment setting
        ]
        
        for pattern in cmd_patterns:
            match = re.match(pattern, cleaned)
            if match:
                cleaned = cleaned[match.end():].strip()
                break
    
    # Find the first JSON opening character
    json_start = None
    for i, char in enumerate(cleaned):
        if char in '{[':
            json_start = i
            break
    
    if json_start is not None:
        cleaned = cleaned[json_start:]
    
    # Remove any trailing non-JSON content
    # Find matching closing brackets/braces for complete JSON
    if cleaned.startswith('{'):
        brace_count = 0
        for i, char in enumerate(cleaned):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and i < len(cleaned) - 1:
                    # Found closing brace, truncate any following content
                    cleaned = cleaned[:i+1]
                    break
    
    # Ensure it's valid JSON
    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError as e:
        _logger.warning(f"JSON still invalid after cleaning: {str(e)}")
        
        # Try to find any JSON-like structure
        json_pattern = r'(\{.*\}|\[.*\])'
        matches = re.findall(json_pattern, cleaned, re.DOTALL)
        
        for match in matches:
            try:
                json.loads(match)
                _logger.info("Found valid JSON after pattern matching")
                return match
            except json.JSONDecodeError:
                continue
        
        _logger.error("Could not fix JSON output, returning original cleaned string")
        return cleaned

def parse_docker_json(output, command=None):
    """
    Parse Docker JSON output with enhanced error handling
    
    Args:
        output (str): Raw command output
        command (str, optional): Command that was executed
        
    Returns:
        dict or list: Parsed JSON data
    """
    # Clean and fix the output
    cleaned_output = fix_json_command_output(output, command)
    
    try:
        result = json.loads(cleaned_output)
        return result
    except json.JSONDecodeError as e:
        _logger.error(f"Failed to parse JSON after cleaning: {str(e)}")
        _logger.error(f"Cleaned output preview: {cleaned_output[:100]}...")
        raise ValueError(f"Failed to parse Docker JSON response: {str(e)}")

def clean_docker_output(output, command=None):
    """
    Clean Docker command output to prepare for processing
    
    Args:
        output (str): Raw command output
        command (str, optional): The command that was used to generate the output
        
    Returns:
        str: Cleaned output
    """
    if not output:
        return ""
    
    # Remove ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned = ansi_escape.sub('', output)
    
    # Normalize line endings
    cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')
    
    # Remove command echo if present
    if command:
        lines = cleaned.split('\n')
        filtered_lines = []
        skip_next = False
        
        for line in lines:
            # Skip empty lines at the beginning
            if not filtered_lines and not line.strip():
                continue
                
            # Skip the line with the command echo
            if command in line:
                skip_next = True  # Sometimes the echo spans multiple lines
                continue
                
            # Skip continuation lines of the command
            if skip_next and line.startswith('+'):
                skip_next = False
                continue
                
            filtered_lines.append(line)
            
        cleaned = '\n'.join(filtered_lines)
    
    # Remove warning lines that often precede Docker JSON output
    warning_pattern = re.compile(r'^WARNING:.*$', re.MULTILINE)
    cleaned = warning_pattern.sub('', cleaned)
    
    # Remove header lines like "name,id,status" that might precede table output
    header_pattern = re.compile(r'^[A-Z]+[A-Z_,]+$', re.MULTILINE)
    cleaned = header_pattern.sub('', cleaned)
    
    # Trim whitespace
    cleaned = cleaned.strip()
    
    return cleaned