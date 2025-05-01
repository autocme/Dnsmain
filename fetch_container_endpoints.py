import requests
import json

# URL for Portainer CE 2.27.4 API documentation in JSON format
url = "https://app.swaggerhub.com/apiproxy/registry/portainer/portainer-ce/2.27.4"

try:
    response = requests.get(url)
    if response.status_code == 200:
        # Parse JSON response
        api_spec = response.json()
        
        # Extract paths related to container management
        paths = api_spec.get('paths', {})
        
        container_endpoints = []
        
        for path, methods in paths.items():
            if 'docker' in path and 'containers' in path:
                for method, details in methods.items():
                    summary = details.get('summary', 'No description')
                    container_endpoints.append({
                        'method': method.upper(),
                        'path': path,
                        'summary': summary
                    })
        
        # Print container management endpoints
        print("Container Management Endpoints:")
        print("==============================")
        
        for endpoint in sorted(container_endpoints, key=lambda x: x['path']):
            print(f"{endpoint['method']} {endpoint['path']}")
            print(f"   {endpoint['summary']}")
            print()
            
    else:
        print(f"Failed to fetch API documentation: {response.status_code}")
        
except Exception as e:
    print(f"Error fetching API documentation: {str(e)}")