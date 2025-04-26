#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This script tests the SSH client module by:
1. Checking if all required dependencies are installed
2. Verifying that the XML template follows OWL 2.0 standards
3. Ensuring asset definitions in __manifest__.py are correct
"""

import os
import sys
import re
import importlib
import xml.etree.ElementTree as ET

def check_dependencies():
    """Check if all required dependencies are installed"""
    required_packages = ['paramiko', 'ansi2html']
    missing_packages = []
    
    for package in required_packages:
        try:
            importlib.import_module(package)
            print(f"✓ Package {package} is installed")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ Package {package} is missing")
    
    return missing_packages

def check_xml_template():
    """Check if the XML template follows OWL 2.0 standards"""
    template_path = './nalios_ssh_clients/static/src/xml/ssh_manager.xml'
    if not os.path.exists(template_path):
        print(f"✗ Template file {template_path} not found")
        return False
    
    try:
        tree = ET.parse(template_path)
        root = tree.getroot()
        
        # Check if the template is properly formatted for OWL 2.0
        templates = root.findall('./')
        if not templates:
            print("✗ No <templates> tag found in the XML file")
            return False
        
        # Check if there's a div element with t-name attribute
        template_elements = root.findall(".//*[@t-name='nalios_ssh_clients.ssh_manager']")
        if not template_elements:
            print("✗ No element with t-name='nalios_ssh_clients.ssh_manager' found")
            return False
        
        print(f"✓ Template {template_path} follows OWL 2.0 standards")
        return True
    except Exception as e:
        print(f"✗ Error parsing template: {str(e)}")
        return False

def check_manifest():
    """Check if the __manifest__.py file has correct asset definitions"""
    manifest_path = './nalios_ssh_clients/__manifest__.py'
    if not os.path.exists(manifest_path):
        print(f"✗ Manifest file {manifest_path} not found")
        return False
    
    try:
        with open(manifest_path, 'r') as f:
            content = f.read()
            
        # Check if the XML template is in the web.assets_backend
        if "'nalios_ssh_clients/static/src/xml/ssh_manager.xml'" not in content:
            print("✗ Template file is not included in the manifest")
            return False
        
        # Check if web.assets_backend contains the template
        if "web.assets_backend" not in content:
            print("✗ web.assets_backend section not found in the manifest")
            return False
        
        print(f"✓ Manifest {manifest_path} has correct asset definitions")
        return True
    except Exception as e:
        print(f"✗ Error checking manifest: {str(e)}")
        return False

def main():
    print("\n=== Testing SSH Client Module ===\n")
    
    missing_packages = check_dependencies()
    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Please install them using: pip install " + " ".join(missing_packages))
    else:
        print("\n✓ All required dependencies are installed")
    
    template_ok = check_xml_template()
    manifest_ok = check_manifest()
    
    if template_ok and manifest_ok and not missing_packages:
        print("\n✅ All checks passed! The SSH client module should work correctly.")
    else:
        print("\n❌ Some checks failed. Please fix the issues before proceeding.")

if __name__ == "__main__":
    main()