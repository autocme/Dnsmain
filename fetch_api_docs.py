import requests
import json

# URL for Portainer CE 2.27.4 API documentation in JSON format
url = "https://app.swaggerhub.com/apiproxy/registry/portainer/portainer-ce/2.27.4"

try:
    response = requests.get(url)
    if response.status_code == 200:
        # Parse JSON response
        api_spec = response.json()
        
        # Extract the main sections of the API
        paths = api_spec.get('paths', {})
        
        # Print API paths by category
        categories = {}
        
        for path, methods in paths.items():
            # Extract first tag as category
            for method, details in methods.items():
                if 'tags' in details and details['tags']:
                    category = details['tags'][0]
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(f"{method.upper()} {path}")
                    break
        
        # Print the categorized endpoints
        print("Portainer CE API 2.27.4 Endpoints by Category:")
        print("=============================================")
        
        for category, endpoints in sorted(categories.items()):
            print(f"\n{category}:")
            print("-" * (len(category) + 1))
            for endpoint in sorted(endpoints):
                print(f"- {endpoint}")
    else:
        print(f"Failed to fetch API documentation: {response.status_code}")
        
except Exception as e:
    print(f"Error fetching API documentation: {str(e)}")