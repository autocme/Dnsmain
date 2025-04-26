#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple test runner for the SSH utils module PPK conversion functionality
This runs outside of Odoo so we can test the conversion functions directly
"""

import sys
from nalios_ssh_clients.models.ssh_utils import (
    is_ppk_format, 
    convert_ppk_to_pem, 
    convert_private_key_if_needed
)

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

def run_tests():
    """
    Run basic tests for the SSH utils module
    """
    print("\n=== Testing SSH Utils Module ===\n")
    
    # Test is_ppk_format
    print("Testing is_ppk_format function:")
    print(f"  PPK format detected:      {is_ppk_format(PPK_EXAMPLE)}")
    print(f"  OpenSSH format detected:  {is_ppk_format(OPENSSH_EXAMPLE)}")
    print(f"  Empty string handled:     {not is_ppk_format('')}")
    print(f"  None value handled:       {not is_ppk_format(None)}")
    
    # Test convert_ppk_to_pem
    print("\nTesting convert_ppk_to_pem function:")
    pem_result = convert_ppk_to_pem(PPK_EXAMPLE)
    print(f"  Conversion returned data: {pem_result is not None}")
    if pem_result:
        has_begin = "-----BEGIN RSA PRIVATE KEY-----" in pem_result
        has_end = "-----END RSA PRIVATE KEY-----" in pem_result
        print(f"  Has BEGIN marker:         {has_begin}")
        print(f"  Has END marker:           {has_end}")
        print("\nSample of converted key:")
        print("  " + pem_result.split('\n')[0])
        print("  " + pem_result.split('\n')[1])
        print("  ...")
        print("  " + pem_result.split('\n')[-2])
        print("  " + pem_result.split('\n')[-1])
    
    # Test convert_private_key_if_needed
    print("\nTesting convert_private_key_if_needed function:")
    ppk_conversion = convert_private_key_if_needed(PPK_EXAMPLE)
    openssh_conversion = convert_private_key_if_needed(OPENSSH_EXAMPLE)
    
    print(f"  PPK key was converted:    {'BEGIN RSA PRIVATE KEY' in ppk_conversion}")
    print(f"  OpenSSH key unchanged:    {openssh_conversion == OPENSSH_EXAMPLE}")
    
    print("\n=== Tests Completed ===\n")

if __name__ == "__main__":
    run_tests()