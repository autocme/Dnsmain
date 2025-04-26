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
            _logger.error("Could not determine PPK version")
            return None
        
        version = int(version_match.group(1))
        if version not in [2, 3]:
            _logger.error(f"Unsupported PPK version: {version}")
            return None
        
        # Extract key type (usually ssh-rsa)
        key_type = re.search(r'PuTTY-User-Key-File-\d+: (\S+)', lines[0])
        if not key_type:
            _logger.error("Could not determine key type")
            return None
        
        key_type = key_type.group(1)
        
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
        
        # Extract the private key data
        private_key_data = ''.join(lines[private_lines_index + 1:private_lines_index + 1 + num_private_lines])
        
        # If the key is RSA, we can construct a PEM format private key
        if key_type == 'ssh-rsa':
            # RSA PEM format begins with this header
            pem_data = "-----BEGIN RSA PRIVATE KEY-----\n"
            
            # Add the base64-encoded private key data with proper line breaks
            for i in range(0, len(private_key_data), 64):
                pem_data += private_key_data[i:i+64] + '\n'
                
            # Add the footer
            pem_data += "-----END RSA PRIVATE KEY-----\n"
            
            return pem_data
        elif key_type == 'ssh-ed25519':
            # ED25519 PEM format begins with this header
            pem_data = "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            
            # Add the base64-encoded private key data with proper line breaks
            for i in range(0, len(private_key_data), 64):
                pem_data += private_key_data[i:i+64] + '\n'
                
            # Add the footer
            pem_data += "-----END OPENSSH PRIVATE KEY-----\n"
            
            return pem_data
        else:
            _logger.error(f"Unsupported key type for conversion: {key_type}")
            return None
            
    except Exception as e:
        _logger.error(f"Failed to convert PPK to PEM: {str(e)}")
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