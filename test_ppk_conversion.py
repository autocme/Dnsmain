#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for PPK to PEM conversion functionality in the SSH client module
"""

import sys
from nalios_ssh_clients.models.ssh_utils import is_ppk_format, convert_ppk_to_pem

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

def test_is_ppk_format():
    """Test the is_ppk_format function"""
    # Test with PPK key
    assert is_ppk_format(PPK_EXAMPLE) == True, "Should identify PPK format"
    
    # Test with OpenSSH key
    assert is_ppk_format(OPENSSH_EXAMPLE) == False, "Should not identify OpenSSH as PPK"
    
    # Test with empty string
    assert is_ppk_format("") == False, "Should handle empty string"
    
    # Test with None
    assert is_ppk_format(None) == False, "Should handle None"
    
    print("✓ is_ppk_format tests passed")

def test_convert_ppk_to_pem():
    """Test the convert_ppk_to_pem function"""
    # Convert PPK to PEM
    result = convert_ppk_to_pem(PPK_EXAMPLE)
    
    # Check that it returns a string
    assert result is not None, "Should return a string, not None"
    
    # Check that it has the PEM format markers
    assert "-----BEGIN RSA PRIVATE KEY-----" in result, "Should contain BEGIN RSA header"
    assert "-----END RSA PRIVATE KEY-----" in result, "Should contain END RSA footer"
    
    print("✓ convert_ppk_to_pem tests passed")

def main():
    """Run all tests"""
    print("\n=== Testing PPK to PEM Conversion ===\n")
    
    try:
        test_is_ppk_format()
        test_convert_ppk_to_pem()
        print("\n✅ All PPK conversion tests passed!\n")
    except AssertionError as e:
        print(f"\n❌ Test failed: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()