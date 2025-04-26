# -*- coding: utf-8 -*-

import logging
import base64
import re
from io import StringIO

_logger = logging.getLogger(__name__)

def is_ppk_format(key_data):
    """
    Check if the key is in PuTTY's PPK format.
    
    Args:
        key_data (str): The key data as string
        
    Returns:
        bool: True if the key is in PPK format, False otherwise
    """
    if not key_data:
        return False
    
    # PPK files start with "PuTTY-User-Key-File"
    return key_data.startswith('PuTTY-User-Key-File')

def convert_ppk_to_pem(ppk_data, passphrase=None):
    """
    Convert a PPK format key to PEM format.
    
    This is a manual implementation of the PPK to PEM conversion.
    PuTTY key format version 2 and 3 are supported.
    
    Args:
        ppk_data (str): The PPK key data as string
        passphrase (str, optional): The passphrase for the key if it's encrypted
        
    Returns:
        str: The key in PEM format or None if conversion failed
    """
    try:
        # Parse PPK file
        lines = ppk_data.strip().split('\n')
        
        # Check header
        if not lines[0].startswith('PuTTY-User-Key-File'):
            _logger.error("Not a valid PPK file")
            return None
        
        # Extract version and algorithm
        version_match = re.search(r'PuTTY-User-Key-File-(\d+)', lines[0])
        if not version_match:
            # Try alternate format: PuTTY-User-Key-File: 2
            version_match = re.search(r'PuTTY-User-Key-File:\s*(\d+)', lines[0])
            if not version_match:
                _logger.error("Could not determine PPK version")
                return None
        
        version = int(version_match.group(1))
        if version not in [2, 3]:
            _logger.error(f"Unsupported PPK version: {version}")
            return None
        
        # Extract key type (usually ssh-rsa)
        if ': ' in lines[0]:
            # Format: PuTTY-User-Key-File-2: ssh-rsa
            key_type_match = re.search(r'PuTTY-User-Key-File-\d+:\s+(\S+)', lines[0])
            if not key_type_match:
                # Try alternate format: PuTTY-User-Key-File: 2 ssh-rsa
                key_type_match = re.search(r'PuTTY-User-Key-File:.*?(\S+)$', lines[0])
        else:
            # Check the second line for the key type
            key_type_match = None
            if len(lines) > 1:
                if lines[1].startswith('Encryption:'):
                    # Check the next line
                    if len(lines) > 2 and not lines[2].startswith('Comment:'):
                        key_type_match = re.match(r'^(\S+)$', lines[2])
                else:
                    key_type_match = re.match(r'^(\S+)$', lines[1])
        
        if not key_type_match:
            _logger.error("Could not determine key type, trying to use 'ssh-rsa' as default")
            key_type = 'ssh-rsa'  # Default to RSA if we can't determine
        else:
            key_type = key_type_match.group(1)
        
        # Log the detected key format information
        _logger.info(f"PPK format detected: version={version}, key_type={key_type}")
        
        # Find the Private-Lines section
        private_lines_index = -1
        for i, line in enumerate(lines):
            if line.startswith('Private-Lines:'):
                private_lines_index = i
                break
                
        if private_lines_index == -1:
            _logger.error("Could not find Private-Lines section")
            return None
            
        # Extract the number of private lines
        num_private_lines = int(lines[private_lines_index].split(':')[1].strip())
        _logger.info(f"Found Private-Lines section at line {private_lines_index}, with {num_private_lines} lines")
        
        # Check if we have enough lines in the file
        if len(lines) < private_lines_index + 1 + num_private_lines:
            _logger.error(f"Not enough lines in the file. Expected at least {private_lines_index + 1 + num_private_lines}, got {len(lines)}")
            return None
        
        # Extract the private key data
        private_key_data = ''.join(lines[private_lines_index + 1:private_lines_index + 1 + num_private_lines])
        
        # If we have no data, something is wrong
        if not private_key_data:
            _logger.error("No private key data extracted")
            return None
            
        _logger.debug(f"Extracted private key data length: {len(private_key_data)}")
        
        # Choose the correct PEM format based on key type
        if key_type.lower() in ['ssh-rsa', 'rsa']:
            # RSA PEM format
            pem_data = "-----BEGIN RSA PRIVATE KEY-----\n"
            
            # Add the base64-encoded private key data with proper line breaks
            for i in range(0, len(private_key_data), 64):
                pem_data += private_key_data[i:i+64] + '\n'
                
            # Add the footer
            pem_data += "-----END RSA PRIVATE KEY-----\n"
            
            return pem_data
        elif key_type.lower() in ['ssh-ed25519', 'ed25519']:
            # ED25519 PEM format
            pem_data = "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            
            # Add the base64-encoded private key data with proper line breaks
            for i in range(0, len(private_key_data), 64):
                pem_data += private_key_data[i:i+64] + '\n'
                
            # Add the footer
            pem_data += "-----END OPENSSH PRIVATE KEY-----\n"
            
            return pem_data
        elif key_type.lower() in ['ssh-dss', 'dss', 'dsa']:
            # DSA PEM format
            pem_data = "-----BEGIN DSA PRIVATE KEY-----\n"
            
            # Add the base64-encoded private key data with proper line breaks
            for i in range(0, len(private_key_data), 64):
                pem_data += private_key_data[i:i+64] + '\n'
                
            # Add the footer
            pem_data += "-----END DSA PRIVATE KEY-----\n"
            
            return pem_data
        elif key_type.lower() in ['ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521', 'ecdsa']:
            # ECDSA PEM format
            pem_data = "-----BEGIN EC PRIVATE KEY-----\n"
            
            # Add the base64-encoded private key data with proper line breaks
            for i in range(0, len(private_key_data), 64):
                pem_data += private_key_data[i:i+64] + '\n'
                
            # Add the footer
            pem_data += "-----END EC PRIVATE KEY-----\n"
            
            return pem_data
        else:
            # For unknown types, try using OpenSSH format as a fallback
            _logger.warning(f"Unknown key type: {key_type}, trying OpenSSH format as fallback")
            pem_data = "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            
            # Add the base64-encoded private key data with proper line breaks
            for i in range(0, len(private_key_data), 64):
                pem_data += private_key_data[i:i+64] + '\n'
                
            # Add the footer
            pem_data += "-----END OPENSSH PRIVATE KEY-----\n"
            
            return pem_data
            
    except Exception as e:
        _logger.error(f"Failed to convert PPK to PEM: {str(e)}")
        import traceback
        _logger.error(traceback.format_exc())
        return None

def convert_private_key_if_needed(key_data, passphrase=None):
    """
    Check if the key is in PPK format and convert it to PEM if needed.
    
    Args:
        key_data (str): The key data as string
        passphrase (str, optional): The passphrase for the key if it's encrypted
        
    Returns:
        str: The key in PEM format (converted or original)
    """
    if is_ppk_format(key_data):
        _logger.info("Detected PPK format, converting to PEM")
        pem_data = convert_ppk_to_pem(key_data, passphrase)
        if pem_data:
            return pem_data
        else:
            _logger.warning("PPK conversion failed, trying to use original key")
    
    # If not PPK or conversion failed, return the original key
    return key_data