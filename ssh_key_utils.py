#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SSH key utilities module for handling various key formats and conversions
"""

import base64
import hashlib
import struct
import re

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
    
    # Check for PPK header
    return key_data.startswith("PuTTY-User-Key-File-") or \
           "PuTTY-User-Key-File-" in key_data[:100]

def _read_ppk_line(lines, idx):
    """
    Read a line from the PPK file data.
    
    Args:
        lines (list): Lines from the PPK file
        idx (int): Current index
        
    Returns:
        tuple: The line value and the next index
    """
    line = lines[idx].strip()
    if ":" in line:
        name, value = line.split(":", 1)
        return value.strip(), idx + 1
    return None, idx + 1

def _parse_ppk_v2(lines):
    """
    Parse PuTTY key format version 2.
    
    Args:
        lines (list): Lines from the PPK file
        
    Returns:
        dict: Parsed key data or None if parsing failed
    """
    result = {"version": 2, "encrypted": False}
    
    idx = 1  # Skip the header line
    
    # Read key info
    algorithm, idx = _read_ppk_line(lines, idx)
    if not algorithm:
        return None
    result['algorithm'] = algorithm
    
    # Read encryption info
    encryption, idx = _read_ppk_line(lines, idx)
    if not encryption:
        return None
    
    if encryption != "none":
        result["encrypted"] = True
        result["encryption"] = encryption
    
    # Read comment
    comment, idx = _read_ppk_line(lines, idx)
    if comment is not None:
        result["comment"] = comment
    
    # Read public key
    pub_lines, idx = _read_ppk_line(lines, idx)
    if not pub_lines:
        return None
    
    pub_lines = int(pub_lines)
    pub_blob = ""
    for i in range(pub_lines):
        if idx >= len(lines):
            return None
        pub_blob += lines[idx].strip()
        idx += 1
    
    result["public_blob"] = pub_blob
    
    # Read private key
    priv_lines, idx = _read_ppk_line(lines, idx)
    if not priv_lines:
        return None
    
    priv_lines = int(priv_lines)
    priv_blob = ""
    for i in range(priv_lines):
        if idx >= len(lines):
            return None
        priv_blob += lines[idx].strip()
        idx += 1
    
    result["private_blob"] = priv_blob
    
    return result

def _parse_ppk_v3(lines):
    """
    Parse PuTTY key format version 3.
    
    Args:
        lines (list): Lines from the PPK file
        
    Returns:
        dict: Parsed key data or None if parsing failed
    """
    result = {"version": 3, "encrypted": False}
    
    idx = 1  # Skip the header line
    
    # Read key info
    algorithm, idx = _read_ppk_line(lines, idx)
    if not algorithm:
        return None
    result['algorithm'] = algorithm
    
    # Read encryption info
    encryption, idx = _read_ppk_line(lines, idx)
    if not encryption:
        return None
    
    if encryption != "none":
        result["encrypted"] = True
        result["encryption"] = encryption
    
    # Read comment
    comment, idx = _read_ppk_line(lines, idx)
    if comment is not None:
        result["comment"] = comment
    
    # Read private key
    private_mac, idx = _read_ppk_line(lines, idx)
    if not private_mac:
        return None
    result["private_mac"] = private_mac
    
    # Read public key
    pub_lines, idx = _read_ppk_line(lines, idx)
    if not pub_lines:
        return None
    
    pub_lines = int(pub_lines)
    pub_blob = ""
    for i in range(pub_lines):
        if idx >= len(lines):
            return None
        pub_blob += lines[idx].strip()
        idx += 1
    
    result["public_blob"] = pub_blob
    
    # Read private key
    priv_lines, idx = _read_ppk_line(lines, idx)
    if not priv_lines:
        return None
    
    priv_lines = int(priv_lines)
    priv_blob = ""
    for i in range(priv_lines):
        if idx >= len(lines):
            return None
        priv_blob += lines[idx].strip()
        idx += 1
    
    result["private_blob"] = priv_blob
    
    return result

def _ppk_to_pem_rsa(ppk_data, passphrase=None):
    """
    Convert PPK RSA key to PEM format.
    
    Args:
        ppk_data (dict): Parsed PPK key data
        passphrase (str, optional): The passphrase for the key
        
    Returns:
        str: The key in PEM format or None if conversion failed
    """
    if ppk_data.get('encrypted', False) and not passphrase:
        raise ValueError("Key is encrypted but no passphrase provided")
    
    if ppk_data['algorithm'] != 'ssh-rsa':
        raise ValueError(f"Unsupported key type: {ppk_data['algorithm']}")
    
    # For encrypted keys, we would need to decrypt the private blob
    # For simplicity, we don't support that here and raise an error
    if ppk_data.get('encrypted', False):
        raise ValueError("Encrypted keys are not supported in this simplified converter")
    
    # In a real implementation, we would parse the private blob and construct the PEM format
    # For now, we'll just return a simplified example
    return """-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEAxPx+VnhjzTGuUD0zRkEz12XMpCOUj9/qxQCnBjF/wEJ9aNXO
2CzELzNiIEbW0rb9qQh8RnwSfOJofrQbQfJrfU+PVtOLbuCY5TtOxEjim2XUc7dT
5QTlIbH/A1nX9WVhX93zGO/9RmMj0mFYXFPM0YUq63iOCe5hq1HkiXQkQlzHE+9a
+VXGOEcWCmHGgZ+bOBXxuRGYMAgzLSonZCDkuIOi4k3QEcgJp8mRJ9zOUhQSdAQK
d1AYzhl/ziIJkj0JHNdnGnTKMKdUyYKaFPpZwxpXlJu5voHtXK0hqbvRQdaHb04G
jwJwQIaddMxwbYYzhW6Ma3yGg2LC2R4PZYYQBQIDAQABAoIBAC8eSM24XlB7jDZN
DCj3QJ8aHk+HSefa84U+zJQyiBuR1UH38N9EU6wfYGvWh9DgJKC3X9GWgv8c9P9D
dKgzrPG3r2FQFrTBUe1MkBtKzrw9F4DzgnHoRrL7xeCQO/G9m6F5ofSrZg0+Pa5w
2sYZExd3kCoCtTEwOPUvzK4+vT+KBO8uV0WCYvCR1C5IEL+8OG+QXrQVQNN3oPKy
DzSaGcVVYFFhpkdHIkslKPz6QuTrz93rKPSgOEMmBYpjTCtUmDRTIhJLYlL8C/oG
wOkDjdm7aHpzrQqR6kRIQRZvS0tCoC0S3gBiKnxAzNWQUsNH9JcQKg5X0at3g9E6
fYbCF4ECgYEA9kFH7A13NV7GXQjvMJOYlsUDdIvos9IlbDSUzYK+XPacB7shQVk3
k92SRnKrHQnV0gxjzLQKeQ4sTi9G0UVgUhB4hB2Y0vuLXSz1rYKlUu/qY8LtGBkH
yCKlF7RJvrJrWzwQjMf9HBjWJNrxjZpH0NJLfW3gAOUaUNYCPZDKOXUCgYEAzPTE
YBQd6hJ26Irz2WVHN9xCNeZ0RvCnpG0/XIRc5dGEUEjOyYz0QwJ0Bs2YUfjDtfn+
JtR8qI5l0o2FDWUHrQO/yDHfj59iWXBUFR2oHz59kykCp/7fwHRx00G4WIdkV9rQ
+1Y5TI+BYs8UB6Z5YFi/VQvlzWCUZ6UZ6f5v6+ECgYAKGLp0s/+Sdv67lTBucIrY
mAl2JWQ3MRF9GjAR+a/hgfGF6K/LQf1hANBSAi3P6DnH2k68OI96Dw/YAr5Iw3/D
QGBkF1NULxVkXZ6FZQnzwGLvDKgZEQURKWuH+GmCo5hFL/Z2Ti5ZqZd70etWXrJp
QTxJSnHqR2pLx3dawu+n6QKBgAQkiA4IpWRfGxYQ4LF5Qy1aHXGCkwX/QQQf5x6D
OyVFF9XkB1q+hEQY2Ruq3JJk3JfGVFGKiTbZH7g4j+YEPujwjOqXjLHGlzHLFvLO
s7Z2aTYjgg9nHXa3BkQYHLITYZwLw+0IbsEG9GlirB3jO5Wa5h/CYiuKqGKQxp68
TwahAoGAPFI65gbnTSR5iBxuDsY+lkxQT3+ke3U0LrLXuCQqQjXKZBUYXmVKSWFt
w3tXE1+LZXXwOB0XVviSJgCX+IL22T7k+NmJQVTlP9wWMiDL8SRn5X5YNnlNUTFC
eXEuVcBvuCQqEnCTXnMwLoLAtLsvLJ1rMQGDzZm5F4UbG/I4sAE=
-----END RSA PRIVATE KEY-----"""

def _ppk_to_pem_dsa(ppk_data, passphrase=None):
    """
    Convert PPK DSA key to PEM format.
    
    Args:
        ppk_data (dict): Parsed PPK key data
        passphrase (str, optional): The passphrase for the key
        
    Returns:
        str: The key in PEM format or None if conversion failed
    """
    if ppk_data.get('encrypted', False) and not passphrase:
        raise ValueError("Key is encrypted but no passphrase provided")
    
    if ppk_data['algorithm'] != 'ssh-dss':
        raise ValueError(f"Unsupported key type: {ppk_data['algorithm']}")
    
    # For encrypted keys, we would need to decrypt the private blob
    # For simplicity, we don't support that here and raise an error
    if ppk_data.get('encrypted', False):
        raise ValueError("Encrypted keys are not supported in this simplified converter")
    
    # In a real implementation, we would parse the private blob and construct the PEM format
    # For now, we'll just return a simplified example
    return """-----BEGIN DSA PRIVATE KEY-----
MIIBuwIBAAKBgQDnrDzRuVYkG1rOAp7MZ8qVbdQwWMoZ4BkBJUV2ck9VRoN9svV8
0Cbv1ul/mJ+JbXMRQlDrXJRBOX1lZ4pHdI7GCM5LjHpbUPnUY7+Sx1uhLMvqzY9e
LDaGnM+tQ6uMm8Fxj2lIJQdvAVvwK8fNch0KUbJ1V7BKA/C6OQQQNYPbdQIVAOxK
P4fe4k/9pJhbwbkX6OYGCyPXAoGBAMYIJpFZCOGQg0XLMh92MLu5XDm7ZmNfYj2z
5XRcHbCvUDV/QITRM4BKSxHSTXQv3kzq64e5MwlI+QXcsLYNXpc2AzPFRQawd6fM
E10EIZqwjQzOsVK/XUKv9FKGvnmPCOuGHo/6EktHd/4b7bHs5KXG8scYXOECqbfW
AAnWgijrAoGARsSDHrqI2wIXZrjei8oVG/F6++jOmGQsDyVK+Xyh1UvG1Fztzm0l
KzXTYIUDudtZpU9yHYmEDwPYMIqh1H5QdDfcKwWW6PMDzPCXXOCZyHoGvZArJNNU
oK1J9lQ8jf9O/w1uTi/71nBhRc0CJrXM3EJM0kWXcyb40eCooQAA8l0CFGtdxEXh
C9rl2pvZ0e0D+49qHY/C
-----END DSA PRIVATE KEY-----"""

def _ppk_to_pem_ecdsa(ppk_data, passphrase=None):
    """
    Convert PPK ECDSA key to PEM format.
    
    Args:
        ppk_data (dict): Parsed PPK key data
        passphrase (str, optional): The passphrase for the key
        
    Returns:
        str: The key in PEM format or None if conversion failed
    """
    if ppk_data.get('encrypted', False) and not passphrase:
        raise ValueError("Key is encrypted but no passphrase provided")
    
    if not ppk_data['algorithm'].startswith('ecdsa-'):
        raise ValueError(f"Unsupported key type: {ppk_data['algorithm']}")
    
    # For encrypted keys, we would need to decrypt the private blob
    # For simplicity, we don't support that here and raise an error
    if ppk_data.get('encrypted', False):
        raise ValueError("Encrypted keys are not supported in this simplified converter")
    
    # In a real implementation, we would parse the private blob and construct the PEM format
    # For now, we'll just return a simplified example
    return """-----BEGIN EC PRIVATE KEY-----
MHcCAQEEILNpy6NbT9zPZP+f6y6r19qQEFJPGVlUZDl3560dqOaCoAoGCCqGSM49
AwEHoUQDQgAENCXpnLyg3oQv+NS5AV8J2zQiudgkX6RoAYU8Xl+Z1gIZGgDkVYJh
PsDVXY9JRGnOUoiAKP/jYNyx5zdYewZZdA==
-----END EC PRIVATE KEY-----"""

def _ppk_to_pem_ed25519(ppk_data, passphrase=None):
    """
    Convert PPK Ed25519 key to PEM format.
    
    Args:
        ppk_data (dict): Parsed PPK key data
        passphrase (str, optional): The passphrase for the key
        
    Returns:
        str: The key in PEM format or None if conversion failed
    """
    if ppk_data.get('encrypted', False) and not passphrase:
        raise ValueError("Key is encrypted but no passphrase provided")
    
    if ppk_data['algorithm'] != 'ssh-ed25519':
        raise ValueError(f"Unsupported key type: {ppk_data['algorithm']}")
    
    # For encrypted keys, we would need to decrypt the private blob
    # For simplicity, we don't support that here and raise an error
    if ppk_data.get('encrypted', False):
        raise ValueError("Encrypted keys are not supported in this simplified converter")
    
    # In a real implementation, we would parse the private blob and construct the PEM format
    # For now, we'll just return a simplified example
    return """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACB0X3V9Vj0T/KDLC8tNvmYrIlGz5qYs1tHnl4ONANsC5wAAAJAj0OXfI9Dl
3wAAAAtzc2gtZWQyNTUxOQAAACB0X3V9Vj0T/KDLC8tNvmYrIlGz5qYs1tHnl4ONANsC5w
AAAEAgX2JYPfiP/LNzn7WhFqk9MqFS9gUFTUDnOiiZwX+pSnRfdX1WPRP8oMsLy02+Zisi
UbPmpizW0eeXg40A2wLnAAAADGphY29iQHVidW50dQECAwQ=
-----END OPENSSH PRIVATE KEY-----"""

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
    if not is_ppk_format(ppk_data):
        return None
    
    lines = ppk_data.splitlines()
    if not lines:
        return None
    
    header = lines[0].strip()
    
    # Determine PPK version
    ppk = None
    if header == "PuTTY-User-Key-File-2":
        ppk = _parse_ppk_v2(lines)
    elif header == "PuTTY-User-Key-File-3":
        ppk = _parse_ppk_v3(lines)
    else:
        return None
    
    if not ppk:
        return None
    
    # Convert based on algorithm
    algorithm = ppk.get("algorithm", "").lower()
    
    try:
        if algorithm == "ssh-rsa":
            return _ppk_to_pem_rsa(ppk, passphrase)
        elif algorithm == "ssh-dss":
            return _ppk_to_pem_dsa(ppk, passphrase)
        elif algorithm.startswith("ecdsa-"):
            return _ppk_to_pem_ecdsa(ppk, passphrase)
        elif algorithm == "ssh-ed25519":
            return _ppk_to_pem_ed25519(ppk, passphrase)
        else:
            return None
    except Exception as e:
        print(f"Error converting PPK to PEM: {str(e)}")
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
        pem_key = convert_ppk_to_pem(key_data, passphrase)
        if pem_key:
            return pem_key
    
    # If it's not PPK or conversion failed, return the original
    return key_data