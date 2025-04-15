#!/usr/bin/env python3
"""
Test script to verify the conversion_method to type field rename
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """
    Main function to validate the field rename
    """
    logger.info("Starting DNS field rename validation")
    
    # Check for XML files with conversion_method
    xml_files = check_xml_files_for_string("conversion_method")
    if xml_files:
        logger.error("Found 'conversion_method' in XML files: %s", xml_files)
    else:
        logger.info("No XML files contain 'conversion_method' - Good!")
    
    # Check for Python files with conversion_method
    py_files = check_py_files_for_string("conversion_method")
    if py_files:
        logger.error("Found 'conversion_method' in Python files: %s", py_files)
    else:
        logger.info("No Python files contain 'conversion_method' - Good!")
    
    # Verify type field exists in the Python files
    type_files = check_py_files_for_string("type = fields.Selection")
    if type_files:
        logger.info("Found 'type' field definition in: %s", type_files)
    else:
        logger.error("Could not find 'type' field definition")
    
    logger.info("Validation complete")

def check_xml_files_for_string(search_string):
    """
    Check XML files for a specific string
    """
    found_files = []
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".xml"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        if search_string in f.read():
                            found_files.append(filepath)
                except (UnicodeDecodeError, IOError) as e:
                    logger.warning(f"Could not read file {filepath}: {e}")
    return found_files

def check_py_files_for_string(search_string):
    """
    Check Python files for a specific string
    """
    found_files = []
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                
                # Skip this test script
                if 'test_dns_rename.py' in filepath:
                    continue
                    
                # Skip cache folders
                if '.cache' in filepath or '.pythonlibs' in filepath:
                    continue
                    
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        if search_string in f.read():
                            found_files.append(filepath)
                except (UnicodeDecodeError, IOError) as e:
                    logger.warning(f"Could not read file {filepath}: {e}")
    return found_files

if __name__ == "__main__":
    main()