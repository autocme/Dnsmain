# -*- coding: utf-8 -*-

"""
Unit tests for PPK to PEM conversion functionality
"""

from odoo.tests import TransactionCase
from ..models.ssh_utils import is_ppk_format, convert_ppk_to_pem, convert_private_key_if_needed

class TestPpkConversion(TransactionCase):
    """Test case for PPK conversion utilities"""
    
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
    
    def test_is_ppk_format(self):
        """Test detection of PPK format"""
        # Test with PPK key
        self.assertTrue(
            is_ppk_format(self.PPK_EXAMPLE), 
            "Should identify PPK format correctly"
        )
        
        # Test with OpenSSH key
        self.assertFalse(
            is_ppk_format(self.OPENSSH_EXAMPLE), 
            "Should not identify OpenSSH as PPK format"
        )
        
        # Test with empty string
        self.assertFalse(
            is_ppk_format(""), 
            "Should handle empty string"
        )
        
        # Test with None
        self.assertFalse(
            is_ppk_format(None), 
            "Should handle None value"
        )
    
    def test_convert_ppk_to_pem(self):
        """Test conversion from PPK to PEM format"""
        # Convert PPK to PEM
        result = convert_ppk_to_pem(self.PPK_EXAMPLE)
        
        # Verify result is not None
        self.assertIsNotNone(result, "Conversion should not return None")
        
        # Verify PEM format markers
        self.assertIn("-----BEGIN RSA PRIVATE KEY-----", result, 
                      "Result should contain BEGIN RSA header")
        self.assertIn("-----END RSA PRIVATE KEY-----", result, 
                      "Result should contain END RSA footer")
    
    def test_convert_if_needed(self):
        """Test the convert_if_needed function"""
        # Test with PPK format
        ppk_result = convert_private_key_if_needed(self.PPK_EXAMPLE)
        self.assertIn("BEGIN RSA PRIVATE KEY", ppk_result, 
                     "PPK should be converted to PEM")
        
        # Test with OpenSSH format - should not change
        openssh_result = convert_private_key_if_needed(self.OPENSSH_EXAMPLE)
        self.assertEqual(openssh_result, self.OPENSSH_EXAMPLE, 
                        "OpenSSH key should not be modified")