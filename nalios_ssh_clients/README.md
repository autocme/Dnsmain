# SSH Client Module for Odoo 17

## Overview
This module adds SSH client functionality to Odoo, allowing users to store SSH connection details,
connect to remote servers, and execute commands directly within Odoo.

## Features
- Store SSH connection credentials (host, port, username, password)
- Support for private key authentication
- Automatic PPK to PEM key format conversion
- Execute commands on remote servers
- Store and run command routines
- Terminal emulation with ANSI color support

## PPK to PEM Key Conversion
The module includes automatic detection and conversion of PuTTY's PPK keys to the OpenSSH PEM format
required by Paramiko. This allows users to directly upload PPK format keys without manual conversion.

### Supported PPK Formats
- PuTTY-User-Key-File-2: ssh-rsa (Standard PPK v2)
- PuTTY-User-Key-File: 2 (Alternate PPK v2 format)
- PuTTY-User-Key-File-3: ssh-rsa (PPK v3)

### Supported Key Types
- RSA (ssh-rsa)
- DSA/DSS (ssh-dss)
- ECDSA (ecdsa-sha2-nistp256, ecdsa-sha2-nistp384, ecdsa-sha2-nistp521)
- Ed25519 (ssh-ed25519)

## Usage

### Connecting with a Password
1. Create a new SSH Client record
2. Enter the hostname, port, username, and password
3. Click "Connect" to establish the connection
4. Use the terminal to execute commands

### Connecting with a Private Key
1. Create a new SSH Client record
2. Enter the hostname, port, and username
3. Upload a private key file (PEM or PPK format)
4. If the key is password-protected, enter the key password
5. Click "Connect" to establish the connection
6. Use the terminal to execute commands

### Creating and Running Command Routines
1. Open an SSH Client record
2. Go to the "Routines" tab
3. Create a new routine with a sequence of commands
4. Run the routine to execute all commands in sequence

## Security Considerations
- SSH credentials are stored in the Odoo database
- Private keys are stored as binary attachments
- Consider using encrypted keys with passphrases for added security
- Access to the module should be restricted to authorized users

## Compatibility
- Fully compatible with Odoo 17.0 Community Edition
- Uses Paramiko library for SSH connections
- Terminal output uses ANSI to HTML conversion for display in the browser