import requests
import json

# URL for Portainer CE 2.27.4 API documentation in JSON format
url = "https://app.swaggerhub.com/apiproxy/registry/portainer/portainer-ce/2.27.4"

try:
    response = requests.get(url)
    if response.status_code == 200:
        # Parse JSON response
        api_spec = response.json()
        
        # Extract custom_templates endpoints
        paths = api_spec.get('paths', {})
        
        custom_templates_endpoints = {}
        for path, methods in paths.items():
            if '/custom_templates' in path:
                custom_templates_endpoints[path] = {}
                for method, details in methods.items():
                    # Extract endpoint summary and parameters
                    summary = details.get('summary', 'No summary available')
                    params = []
                    for param in details.get('parameters', []):
                        params.append({
                            'name': param.get('name'),
                            'in': param.get('in'),
                            'required': param.get('required', False),
                            'type': param.get('schema', {}).get('type') if 'schema' in param else param.get('type')
                        })
                    
                    # Extract request body if available
                    request_body = None
                    if 'requestBody' in details:
                        content = details['requestBody'].get('content', {})
                        schema_ref = None
                        for content_type, content_details in content.items():
                            if 'schema' in content_details:
                                schema = content_details['schema']
                                if '$ref' in schema:
                                    schema_ref = schema['$ref'].split('/')[-1]
                                    break
                        request_body = schema_ref
                    
                    custom_templates_endpoints[path][method] = {
                        'summary': summary,
                        'parameters': params,
                        'requestBody': request_body
                    }
        
        # Get schemas for request bodies
        schemas = api_spec.get('components', {}).get('schemas', {})
        relevant_schemas = {}
        for path, methods in custom_templates_endpoints.items():
            for method, details in methods.items():
                if details['requestBody'] and details['requestBody'] in schemas:
                    relevant_schemas[details['requestBody']] = schemas[details['requestBody']]
        
        # Print custom_templates endpoints details
        print("Portainer CE API 2.27.4 - Custom Templates Endpoints:")
        print("===================================================")
        
        for path, methods in sorted(custom_templates_endpoints.items()):
            for method, details in sorted(methods.items()):
                print(f"\n{method.upper()} {path}")
                print(f"Summary: {details['summary']}")
                
                if details['parameters']:
                    print("Parameters:")
                    for param in details['parameters']:
                        required = "(required)" if param.get('required') else "(optional)"
                        print(f"  - {param.get('name')} [{param.get('in')}] {required}: {param.get('type')}")
                
                if details['requestBody']:
                    print(f"Request Body: {details['requestBody']}")
                    if details['requestBody'] in relevant_schemas:
                        schema = relevant_schemas[details['requestBody']]
                        print("  Schema Properties:")
                        properties = schema.get('properties', {})
                        for prop_name, prop_details in properties.items():
                            prop_type = prop_details.get('type', 'object')
                            prop_desc = prop_details.get('description', 'No description')
                            print(f"    - {prop_name} ({prop_type}): {prop_desc}")
                
                print("-" * 50)
                
        # Print separately the details of the create/string endpoint
        print("\nDETAILS FOR CREATE/STRING ENDPOINT:")
        print("==================================")
        create_string_path = "/custom_templates/create/string"
        if create_string_path in custom_templates_endpoints:
            methods = custom_templates_endpoints[create_string_path]
            for method, details in methods.items():
                if details['requestBody'] and details['requestBody'] in relevant_schemas:
                    schema = relevant_schemas[details['requestBody']]
                    print(f"Schema for {details['requestBody']}:")
                    print(json.dumps(schema, indent=2))
    else:
        print(f"Failed to fetch API documentation: {response.status_code}")
        
except Exception as e:
    print(f"Error fetching API documentation: {str(e)}")