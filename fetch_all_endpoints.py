import requests
import json

# URL for Portainer CE 2.27.4 API documentation in JSON format
url = "https://app.swaggerhub.com/apiproxy/registry/portainer/portainer-ce/2.27.4"

try:
    response = requests.get(url)
    if response.status_code == 200:
        # Parse JSON response
        api_spec = response.json()
        
        # Extract all paths
        paths = api_spec.get('paths', {})
        
        # Print all endpoints
        print("All API Endpoints:")
        print("=================")
        
        for path, methods in sorted(paths.items()):
            print(f"\nPATH: {path}")
            for method, details in methods.items():
                summary = details.get('summary', 'No description')
                print(f"  {method.upper()}: {summary}")
                
                # Check if this is a proxy to Docker API
                if 'docker' in path and '/endpoints/' in path:
                    print("  (Docker API proxy endpoint)")
                    
    else:
        print(f"Failed to fetch API documentation: {response.status_code}")
        
except Exception as e:
    print(f"Error fetching API documentation: {str(e)}")