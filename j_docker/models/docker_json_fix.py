import re
import json
import logging

_logger = logging.getLogger(__name__)

def clean_docker_output(output):
    """Clean Docker command output by removing ANSI codes and command echo

    Args:
        output (str): Raw output from Docker command

    Returns:
        str: Cleaned output
    """
    if not output:
        return ""
        
    # Remove command echo
    lines = output.split('\n')
    cleaned_lines = []
    skip_current = False
    docker_command_pattern = re.compile(r'^(sudo )?docker.*')
    
    for line in lines:
        # Skip docker command echoes
        if docker_command_pattern.match(line):
            skip_current = True
            continue
        
        # Skip lines after a docker command until we find content
        if skip_current:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                skip_current = False
            else:
                continue
                
        cleaned_lines.append(line)
        
    # Join lines back
    cleaned_output = '\n'.join(cleaned_lines)
    
    # Remove ANSI color codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned_output = ansi_escape.sub('', cleaned_output)
    
    return cleaned_output.strip()

def fix_json_command_output(output):
    """Clean up and fix JSON output from Docker command

    Args:
        output (str): Raw output from Docker command that should contain JSON

    Returns:
        str: Fixed JSON string ready for parsing
    """
    # Skip if output is empty
    if not output or not output.strip():
        return '{}'
        
    # Find and remove command echo from the output
    lines = output.split('\n')
    cleaned_lines = []
    skip_current = False
    docker_command_pattern = re.compile(r'^(sudo )?docker.*')
    
    for line in lines:
        # Skip docker command echoes
        if docker_command_pattern.match(line):
            skip_current = True
            continue
        
        # Skip lines after a docker command until we find JSON
        if skip_current:
            if line.strip().startswith('{') or line.strip().startswith('['):
                skip_current = False
            else:
                continue
                
        cleaned_lines.append(line)
        
    # Join lines back
    json_text = '\n'.join(cleaned_lines)
    
    # Remove ANSI color codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    json_text = ansi_escape.sub('', json_text)
    
    # Find the first open bracket or curly brace
    start_index = -1
    for char in ['{', '[']:
        found_index = json_text.find(char)
        if found_index != -1 and (start_index == -1 or found_index < start_index):
            start_index = found_index
            
    if start_index != -1:
        json_text = json_text[start_index:]
    
    # Find the last close bracket or curly brace
    end_index = -1
    for char in ['}', ']']:
        found_index = json_text.rfind(char)
        if found_index != -1 and found_index > end_index:
            end_index = found_index
            
    if end_index != -1:
        json_text = json_text[:end_index+1]
        
    # Remove trailing commas which are invalid in JSON
    json_text = re.sub(r',\s*([}\]])', r'\1', json_text)
    
    # Try to validate JSON
    try:
        # If the output is valid, just return it
        json.loads(json_text)
        return json_text
    except json.JSONDecodeError as e:
        _logger.warning(f"JSON validation failed: {str(e)}. Attempting fixes...")
        
        # Common Docker API response issues:
        
        # 1. Handle inconsistent quotes (replace single with double quotes)
        json_text = json_text.replace("'", '"')
        
        # 2. Fix unquoted keys 
        json_text = re.sub(r'(\s*)(\w+)(\s*):(\s*)', r'\1"\2"\3:\4', json_text)
        
        # 3. Fix trailing commas in arrays
        json_text = re.sub(r',(\s*[\]}])', r'\1', json_text)
        
        # 4. Handle any remaining whitespace or control characters at start/end
        json_text = json_text.strip()
        
        # Verify our fixes worked
        try:
            json.loads(json_text)
            return json_text
        except json.JSONDecodeError:
            # Last resort - try to find a valid JSON object or array in the output
            pattern = r'({[\s\S]*?})|([\[\s\S]*?])'
            matches = re.findall(pattern, json_text)
            
            for match in matches:
                for potential_json in match:
                    if not potential_json:
                        continue
                        
                    try:
                        json.loads(potential_json)
                        return potential_json
                    except json.JSONDecodeError:
                        continue
                        
            # If we got here, we couldn't fix it
            _logger.error(f"Could not fix JSON output: {output}")
            return '{}'