# AWS Boto Base Module for Odoo 17

## Overview

The AWS Boto Base module serves as a foundation for all AWS service integrations in Odoo 17. It provides a centralized management system for AWS credentials, standardized API access patterns, comprehensive error handling, and detailed logging of AWS operations.

This module is designed to be highly flexible and reusable, allowing other modules to easily integrate with any AWS service without having to reimplement common AWS functionality.

## Features

- **Credential Management**: Securely store and manage multiple AWS credentials
- **Multiple Authentication Methods**: Support for access keys, profiles, instance profiles, and environment variables
- **Service Coverage**: Compatible with 60+ AWS services
- **Standardized API Access**: Consistent patterns for accessing AWS services
- **Error Handling**: Comprehensive error handling and user-friendly error messages
- **Operation Logging**: Detailed logging of AWS operations for auditing and debugging
- **Region Management**: Utilities for working with AWS regions
- **IAM Integration**: Track and validate IAM information associated with credentials
- **Developer Tools**: Helper functions for common AWS tasks

## Components

### Models

- **aws.credentials**: Store and manage AWS credentials
- **aws.service**: Track available AWS services
- **aws.operation.log**: Log AWS operations for auditing
- **aws.utils**: Utility functions for common AWS tasks
- **aws.client.mixin**: Mixin for easy AWS client integration
- **aws.service.logger**: Mixin for advanced AWS operation logging
- **aws.service.implementation.mixin**: Mixin for implementing specific AWS services

### Mixins

Mixins provide reusable functionality that can be included in other models:

#### aws.client.mixin

Base functionality for accessing AWS services:

```python
# Example usage in a model
class MyModel(models.Model):
    _name = 'my.model'
    _inherit = ['aws.client.mixin']
    
    def use_s3(self):
        # Get an S3 client
        s3_client = self.get_aws_client('s3')
        
        # List buckets
        buckets = s3_client.list_buckets()
```

#### aws.service.logger

Advanced logging functionality for AWS operations:

```python
# Example usage in a model
class MyModel(models.Model):
    _name = 'my.model'
    _inherit = ['aws.service.logger']
    
    def upload_to_s3(self, bucket, key, data):
        # Execute S3 operation with logging
        success, result = self.aws_operation_with_logging(
            service_name='s3',
            operation='put_object',
            with_result=True,
            Bucket=bucket,
            Key=key,
            Body=data
        )
        return success
```

#### aws.service.implementation.mixin

Template for implementing AWS service integrations:

```python
# Example usage in a model
class S3BucketManager(models.Model):
    _name = 's3.bucket.manager'
    _inherit = ['aws.service.implementation.mixin']
    
    def get_bucket_list(self):
        # Get S3 client using this record's credentials and region
        client = self.get_service_client('s3')
        return client.list_buckets()
```

## Security

The module provides two security groups:

- **AWS User**: Users who can access AWS resources but not manage credentials
- **AWS Manager**: Users who can manage AWS credentials and configurations

## Integration

To use this module in your own AWS integration module:

1. Add a dependency on `boto_base` in your module's `__manifest__.py`:

```python
'depends': ['boto_base'],
```

2. Use the provided mixins in your models:

```python
from odoo import api, fields, models

class MyAWSService(models.Model):
    _name = 'my.aws.service'
    _inherit = ['aws.service.implementation.mixin']
    
    # Add your model fields here
    
    def my_aws_function(self):
        # Get AWS client
        client = self.get_service_client('my-aws-service')
        
        # Use the client
        result = client.some_operation()
        return result
```

## Best Practices

1. Always use the provided mixins rather than directly creating boto3 clients
2. Use the logging functionality to track AWS operations
3. Handle AWS errors properly using the error handling utilities
4. Store AWS-specific configuration in your module, not in the boto_base module
5. Use the AWS operation log for auditing and debugging

## Requirements

- Odoo 17.0
- Python 3.10+
- boto3
- botocore

## License

LGPL-3

## Authors

- JAAH