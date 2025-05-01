import requests
import json

# URL for Portainer CE 2.27.4 API documentation in JSON format
url = "https://app.swaggerhub.com/apiproxy/registry/portainer/portainer-ce/2.27.4"

try:
    response = requests.get(url)
    if response.status_code == 200:
        # Parse JSON response
        api_spec = response.json()
        
        # Get the schemas from components
        schemas = api_spec.get('components', {}).get('schemas', {})
        
        # Check the request body for the create/string endpoint
        create_string_path = "/custom_templates/create/string"
        create_string_method = "post"
        
        # Find the schema for the request body
        request_body_schema = None
        request_body_name = None
        
        if create_string_path in api_spec.get('paths', {}):
            methods = api_spec['paths'][create_string_path]
            if create_string_method in methods:
                details = methods[create_string_method]
                if 'requestBody' in details:
                    content = details['requestBody'].get('content', {})
                    for content_type, content_details in content.items():
                        if 'schema' in content_details:
                            schema = content_details['schema']
                            if '$ref' in schema:
                                request_body_name = schema['$ref'].split('/')[-1]
                                request_body_schema = schemas.get(request_body_name)
                                break
        
        # Print the schema for the request body
        if request_body_schema:
            print(f"Schema for {request_body_name}:")
            print(json.dumps(request_body_schema, indent=2))
            
            # Extract properties
            properties = request_body_schema.get('properties', {})
            print("\nProperties:")
            for prop_name, prop_details in properties.items():
                prop_type = prop_details.get('type', 'object')
                prop_desc = prop_details.get('description', 'No description')
                print(f" - {prop_name} ({prop_type}): {prop_desc}")
        else:
            print("Could not find schema for the request body")
            
        # Also check for other template-related schemas
        template_schemas = {}
        for schema_name, schema in schemas.items():
            if 'template' in schema_name.lower():
                template_schemas[schema_name] = schema
                
        # Print all template-related schemas
        print("\nAll Template-Related Schemas:")
        for schema_name, schema in template_schemas.items():
            print(f"\nSchema: {schema_name}")
            properties = schema.get('properties', {})
            print("Properties:")
            for prop_name, prop_details in properties.items():
                prop_type = prop_details.get('type', 'object')
                prop_desc = prop_details.get('description', 'No description')
                print(f" - {prop_name} ({prop_type}): {prop_desc}")
    else:
        print(f"Failed to fetch API documentation: {response.status_code}")
        
except Exception as e:
    print(f"Error fetching API documentation: {str(e)}")