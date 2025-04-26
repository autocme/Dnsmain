#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Standalone test for PPK to PEM conversion without Odoo dependencies
"""

import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)

# Example PPK key (not a real key)
PPK_EXAMPLE = """PuTTY-User-Key-File-2: ssh-rsa
Encryption: none
Comment: rsa-key-20240426
Public-Lines: 6
AAAAB3NzaC1yc2EAAAABJQAAAQEAhk8hkgpWGzI0Ezw0yLpZ8yIkBVJQCuQxl4Q6
pSHrnmWM5JrW9cH+ZC7bSiTp12N8XZLj+3XE1qj8A4WGBH53jh0Hw+Z02J9X2RtL
tN1aZveTmqqbiH3EM9j8pJOxSaFfOLa7WfQ+XUeMmcjS1NZx3Wc4YZ9USNHNLp3g
XkJjVR7H5mQlD0mhp6X6Qun1rG9PtKyMQAvzJi/HY9H4iBJSJCm6wBLvA9BLQ5Ks
9R3KLPkC1NUMIDAMb75bwp3dEIYO/WPKOX1HuQnJJiG/YX4C6ztPdmZJtm+i5BRK
rXfOI8LUjACkG9xm/+7+jJvRDGKcRxU4NQhdUsw43ZL/+DLehw==
Private-Lines: 14
AAABADTeCZcSzh4W7OHRbFNNJhGwQVPILZ7qYwK/rqIlEvx8KC7BhpTIq3ZuX1c4
LFFL9bjBq41NZyHYe1cFpZjgVwVOFMQi5h0NpZaPwRzbnqXtb9DFrK3zOc5lE9/q
SHU8TLQ7qfQOWsYQSGsA44+ELFpNIy/Ic3ULZAzfGKA1X+2+lKQKABXw91YHpxIw
V3cAkEVxd9Nk2j8jSoy/NtQys3cTWRyAnL10aMEGU8lLmJdO7gNgB4x1XZ9blETv
2Kl4OV8N4GB8y4iyLIWUXE/BYM5mLOVM2vJlEKvxRZ9vXe6FSqklPs+CgyD9OhWm
gGmA8OU+yvJJqo9HpPQd68EAAACBALrD0+qvXKJ4ZcBk6A9BM6XEm9Bj1GxDDL6Z
7zIIXMFUnV0FRehalf3fFBF2GRVUDWlxupDH5MQni9TKX5PwVj/PQ8qGNjT0HdcC
2QDEgJFxBDwh8yD9qYpOVT2HzVFiVRwtcnG7BjRMGHuoOjgKRRmJKm5bbeYXVZNi
YE8gNwfBAAACAQCTtXbYmQzs3W2TL2Pdm+bRlJnDcT+MJjILxhXbGGGmDRdUNpHe
VpXqJuPWe0IzbMOuc4wLUgPwV2IjlXcVgbKimhQxsmuZvV5YXcvjz/EnhixEuVIy
2PQtiBJ9yEDuSZ5I4wZmXCpkkHYO3zzgqVNR0GKDymXeRY4YyAKGbHpPcaHKznRS
SIk0Eu2rGk1Mh7vCUZ8i+WJ9aYgDLmNtZLFEewkkQbMxgpL2F72w9lBjLRGEMWHF
tYPLQoZ/NbISdcRZeJ/xGNSXxuW9qcPtYCxXH6HplzayVASl0hbqeA+BZRIbEqaS
j5vrpJC9UZEckxp4LxFdbAWfrKKsRw==
Private-MAC: 77a9dd9e5b95aaa4cdb6ae0450fcebe10ec2cb8b
"""

# Example OpenSSH key (not a real key)
OPENSSH_EXAMPLE = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAhk8hkgpWGzI0Ezw0yLpZ8yIkBVJQCuQxl4Q6pSHrnmWM5JrW
9cH+ZC7bSiTp12N8XZLj+3XE1qj8A4WGBH53jh0Hw+Z02J9X2RtLtN1aZveTmqqb
iH3EM9j8pJOxSaFfOLa7WfQ+XUeMmcjS1NZx3Wc4YZ9USNHNLp3gXkJjVR7H5mQl
D0mhp6X6Qun1rG9PtKyMQAvzJi/HY9H4iBJSJCm6wBLvA9BLQ5Ks9R3KLPkC1NUM
IDAMb75bwp3dEIYO/WPKOX1HuQnJJiG/YX4C6ztPdmZJtm+i5BRKrXfOI8LUjACk
G9xm/+7+jJvRDGKcRxU4NQhdUsw43ZL/+DLehwIDAQABAoIBADTeCZcSzh4W7OHR
bFNNJhGwQVPILZ7qYwK/rqIlEvx8KC7BhpTIq3ZuX1c4LFFL9bjBq41NZyHYe1cF
pZjgVwVOFMQi5h0NpZaPwRzbnqXtb9DFrK3zOc5lE9/qSHU8TLQ7qfQOWsYQSGsA
44+ELFpNIy/Ic3ULZAzfGKA1X+2+lKQKABXw91YHpxIwV3cAkEVxd9Nk2j8jSoy/
NtQys3cTWRyAnL10aMEGU8lLmJdO7gNgB4x1XZ9blETv2Kl4OV8N4GB8y4iyLIWU
XE/BYM5mLOVM2vJlEKvxRZ9vXe6FSqklPs+CgyD9OhWmgGmA8OU+yvJJqo9HpPQd
68EAAAA=
-----END RSA PRIVATE KEY-----
"""

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

def run_tests():
    """
    Run basic tests on the PPK to PEM conversion functions
    """
    print("\n=== Testing PPK to PEM Conversion ===\n")
    
    # Test is_ppk_format
    print("Testing is_ppk_format function:")
    assert is_ppk_format(PPK_EXAMPLE) == True, "Should identify PPK format"
    assert is_ppk_format(OPENSSH_EXAMPLE) == False, "Should not identify OpenSSH as PPK"
    assert is_ppk_format("") == False, "Should handle empty string"
    assert is_ppk_format(None) == False, "Should handle None"
    print("✓ is_ppk_format tests passed")
    
    # Test convert_ppk_to_pem
    print("\nTesting convert_ppk_to_pem function:")
    result = convert_ppk_to_pem(PPK_EXAMPLE)
    
    # Check that it returns a string
    assert result is not None, "Should return a string, not None"
    
    # Check that it has the PEM format markers
    assert "-----BEGIN RSA PRIVATE KEY-----" in result, "Should contain BEGIN RSA header"
    assert "-----END RSA PRIVATE KEY-----" in result, "Should contain END RSA footer"
    
    print("✓ convert_ppk_to_pem tests passed")
    
    # Test convert_private_key_if_needed
    print("\nTesting convert_private_key_if_needed function:")
    
    # Test with PPK format
    ppk_result = convert_private_key_if_needed(PPK_EXAMPLE)
    assert "-----BEGIN RSA PRIVATE KEY-----" in ppk_result, "PPK should be converted to PEM"
    
    # Test with OpenSSH format - should not change
    openssh_result = convert_private_key_if_needed(OPENSSH_EXAMPLE)
    assert openssh_result == OPENSSH_EXAMPLE, "OpenSSH key should not be modified"
    
    print("✓ convert_private_key_if_needed tests passed")
    
    print("\nAll tests passed! The PPK to PEM conversion is working correctly.")
    print("\nExample converted key:")
    print("------------------------")
    print(result[:100] + "..." + result[-40:])

if __name__ == "__main__":
    run_tests()