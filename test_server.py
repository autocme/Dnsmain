#!/usr/bin/env python3
"""
Minimal test server to validate Portainer environment creation
"""
import sys
import os
import json
from flask import Flask, request, jsonify

# Add current directory to Python path for imports
sys.path.insert(0, os.getcwd())

app = Flask(__name__)

# Mock Portainer API endpoints for testing
@app.route('/api/endpoints', methods=['POST'])
def create_endpoint():
    """Mock Portainer endpoint creation API"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['Name', 'EndpointType', 'URL']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Missing required field: {field}'}), 400
    
    # Mock successful response
    response = {
        'Id': 1,
        'Name': data['Name'],
        'Type': data['EndpointType'],
        'URL': data['URL'],
        'PublicURL': data.get('PublicURL', ''),
        'GroupId': data.get('GroupID', 1),
        'TLS': data.get('TLS', False),
        'TLSSkipVerify': data.get('TLSSkipVerify', False),
        'TLSSkipClientVerify': data.get('TLSSkipClientVerify', False),
        'TagIds': data.get('TagIDs', []),
        'Status': 1,  # Connected
        'Snapshots': []
    }
    
    print(f"Mock Portainer API - Created endpoint: {json.dumps(response, indent=2)}")
    return jsonify(response), 201

@app.route('/api/system/status', methods=['GET'])
def system_status():
    """Mock Portainer system status API"""
    return jsonify({
        'Version': '2.27.4',
        'DatabaseType': 'boltdb',
        'InstanceID': 'mock-instance'
    })

@app.route('/api/system/info', methods=['GET'])
def system_info():
    """Mock Portainer system info API"""
    return jsonify({
        'Edition': 'CE',
        'Version': '2.27.4'
    })

@app.route('/api/endpoints', methods=['GET'])
def list_endpoints():
    """Mock list endpoints API"""
    return jsonify([])

# Test environment creation logic
def test_environment_creation():
    """Test the environment creation payload"""
    print("Testing environment creation payload...")
    
    # Simulate form data
    vals = {
        'name': 'Test Docker Environment',
        'url': '192.168.1.100',
        'type': '1',  # Docker Standalone
        'connection_method': 'agent',
        'platform': 'linux',
        'public_url': '',
        'group_id': 1
    }
    
    # Prepare data for Portainer API (same logic as in the model)
    endpoint_type = int(vals.get('type', '1'))
    portainer_endpoint_type = 2 if vals.get('connection_method', 'agent') == 'agent' else endpoint_type
    
    environment_data = {
        'Name': vals['name'],
        'EndpointType': portainer_endpoint_type,
        'URL': f"tcp://{vals['url']}:9001",
        'PublicURL': vals.get('public_url', ''),
        'GroupID': int(vals.get('group_id', 1)),
        'TLS': False,
        'TLSSkipVerify': False,
        'TLSSkipClientVerify': False,
        'TagIDs': []
    }
    
    print(f"Environment creation payload: {json.dumps(environment_data, indent=2)}")
    
    # Test payload validation
    required_fields = ['Name', 'EndpointType', 'URL']
    missing_fields = [field for field in required_fields if field not in environment_data]
    
    if missing_fields:
        print(f"ERROR: Missing required fields: {missing_fields}")
        return False
    
    print("✓ Payload validation passed")
    return True

if __name__ == '__main__':
    # Test the environment creation logic
    test_environment_creation()
    
    print("\nStarting mock Portainer API server on port 5000...")
    print("This will help debug the 'Invalid request payload' error")
    app.run(host='0.0.0.0', port=5000, debug=True)