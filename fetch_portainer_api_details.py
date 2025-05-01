import requests
import json

# URL for Portainer CE 2.27.4 API documentation in JSON format
url = "https://app.swaggerhub.com/apiproxy/registry/portainer/portainer-ce/2.27.4"

try:
    response = requests.get(url)
    if response.status_code == 200:
        # Parse JSON response
        api_spec = response.json()
        
        # Define the categories we want to focus on for control features
        focus_categories = [
            'endpoints',
            'docker',
            'containers',
            'images',
            'volumes',
            'networks',
            'stacks',
            'custom_templates',
            'templates'
        ]
        
        # Extract paths and organize them by tags/categories
        paths = api_spec.get('paths', {})
        
        # Track all categories found
        all_categories = set()
        categorized_endpoints = {}
        
        for path, methods in paths.items():
            for method, details in methods.items():
                if 'tags' in details and details['tags']:
                    category = details['tags'][0]
                    all_categories.add(category)
                    
                    # Check if this category is in our focus list
                    for focus in focus_categories:
                        if focus in category.lower() or focus in path.lower():
                            if category not in categorized_endpoints:
                                categorized_endpoints[category] = []
                            
                            # Get operation summary
                            summary = details.get('summary', 'No description')
                            
                            # Add the endpoint
                            categorized_endpoints[category].append({
                                'method': method.upper(),
                                'path': path,
                                'summary': summary
                            })
                            break
        
        # Print all categories
        print("All API Categories:")
        print("==================")
        for category in sorted(all_categories):
            print(f"- {category}")
        
        print("\n\nDetailed Control Endpoints by Category:")
        print("=====================================")
        for category, endpoints in sorted(categorized_endpoints.items()):
            print(f"\n{category}:")
            print("-" * len(category))
            
            for endpoint in sorted(endpoints, key=lambda x: x['path']):
                print(f"{endpoint['method']} {endpoint['path']}")
                print(f"   {endpoint['summary']}")
        
        # Find all container control operations
        print("\n\nContainer Control Operations:")
        print("============================")
        container_operations = []
        for path, methods in paths.items():
            if '/containers/' in path:
                for method, details in methods.items():
                    if method.lower() == 'post' and 'summary' in details:
                        summary = details.get('summary', '')
                        if any(action in summary.lower() for action in ['start', 'stop', 'restart', 'kill', 'pause', 'unpause', 'exec']):
                            container_operations.append({
                                'method': method.upper(),
                                'path': path,
                                'summary': summary
                            })
        
        for op in sorted(container_operations, key=lambda x: x['path']):
            print(f"{op['method']} {op['path']}")
            print(f"   {op['summary']}")
        
        # Find detailed information about stack management
        print("\n\nStack Management Operations:")
        print("============================")
        stack_operations = []
        for path, methods in paths.items():
            if '/stacks/' in path:
                for method, details in methods.items():
                    summary = details.get('summary', '')
                    stack_operations.append({
                        'method': method.upper(),
                        'path': path,
                        'summary': summary
                    })
        
        for op in sorted(stack_operations, key=lambda x: x['path']):
            print(f"{op['method']} {op['path']}")
            print(f"   {op['summary']}")
        
    else:
        print(f"Failed to fetch API documentation: {response.status_code}")
        
except Exception as e:
    print(f"Error fetching API documentation: {str(e)}")