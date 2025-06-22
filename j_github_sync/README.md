# GitHub Sync Module

## Overview
The GitHub Sync module provides integration with a GitHub Sync Server API for managing repositories, logs, and synchronization operations within Odoo 17.0.

## Features

### Core Functionality
- **GitHub Sync Server Management**: Configure and manage GitHub Sync Server connections
- **Repository Synchronization**: Sync and manage GitHub repositories
- **Operation Logging**: Track all sync operations with detailed logs
- **Demo Mode**: Test functionality without external server dependency
- **Request Details Tracking**: Monitor API request/response details

### Models

#### 1. GitHub Sync Server (`github.sync.server`)
**Fields:**
- `gss_name`: Server name
- `gss_server_url`: Server URL (e.g., http://3.110.88.87:5000)
- `gss_api_key`: Authentication API key
- `gss_active`: Server status
- `gss_demo_mode`: Enable demo mode for testing
- `gss_server_status`: Current server status
- `gss_last_sync`: Last synchronization timestamp
- `gss_last_request_details`: Raw API response details
- `gss_company_id`: Company association

**Methods:**
- `action_test_connection()`: Test server connectivity
- `action_sync_repositories()`: Synchronize repositories from server
- `action_sync_logs()`: Synchronize operation logs
- `_make_request()`: Handle API requests with error handling
- `_simulate_api_response()`: Demo mode API simulation

#### 2. GitHub Repository (`github.repository`)
**Fields:**
- `gr_external_id`: External repository ID
- `gr_name`: Repository name
- `gr_url`: Repository URL
- `gr_description`: Repository description
- `gr_private`: Privacy status
- `gr_active`: Repository status
- `gr_server_id`: Associated sync server
- `gr_company_id`: Company association

**Methods:**
- `action_sync_repository()`: Sync individual repository

#### 3. GitHub Sync Log (`github.sync.log`)
**Fields:**
- `gsl_external_id`: External log ID
- `gsl_timestamp`: Log timestamp
- `gsl_level`: Log level (debug, info, warning, error, critical)
- `gsl_status`: Operation status (success, error, warning, pending, failed)
- `gsl_operation_type`: Operation type (pull, clone, restart, webhook, sync, deploy, backup, other)
- `gsl_message`: Log message
- `gsl_operation`: Operation identifier
- `gsl_repository`: Associated repository
- `gsl_details`: Additional operation details
- `gsl_server_id`: Associated sync server
- `gsl_company_id`: Company association

### Security Groups
- **GitHub Sync User**: Basic access to view records
- **GitHub Sync Manager**: Full access to create, read, update, delete

### Demo Mode Features
When demo mode is enabled on a server:
- Simulates API responses without external connection
- Generates 22 sample log entries with varied operation types and statuses
- Creates 2 demo repositories (public and private)
- Provides realistic test data for development

### API Integration
The module integrates with GitHub Sync Server API endpoints:
- `/api/status` - Server status check
- `/api/repositories` - Repository listing
- `/api/logs` - Operation logs
- `/api/repositories/{id}/sync` - Repository synchronization

### Views and Navigation
- **Servers**: Main configuration interface with connection testing
- **Repositories**: Repository management with sync capabilities
- **Operation Logs**: Comprehensive log viewing with filtering by operation type and status
- **Request Details**: Dedicated page for API response inspection

### Error Handling
- Connection timeout handling with user-friendly messages
- Authentication failure detection
- Network error recovery suggestions
- Demo mode fallback recommendations

### Field Naming Convention
- `gss_`: GitHub Sync Server fields
- `gr_`: GitHub Repository fields  
- `gsl_`: GitHub Sync Log fields

### Installation Requirements
- Odoo 17.0
- Base modules: `base`, `web`
- Python requests library (already included in dependencies)

### Configuration Steps
1. Install the module
2. Navigate to GitHub Sync > Servers
3. Create a new server configuration
4. Enable demo mode for testing or configure real server details
5. Test connection and sync data

### Technical Implementation
- **DateTime Parsing**: Handles ISO format timestamps with timezone handling
- **Duplicate Prevention**: External ID constraints prevent duplicate records
- **Batch Operations**: Efficient bulk synchronization
- **Logging**: Comprehensive request/response logging
- **Error Recovery**: Graceful handling of API failures

### Menu Structure
```
GitHub Sync
├── Servers
├── Repositories  
└── Operation Logs
```

### Dependencies
```python
'depends': ['base', 'web']
```

### Files Structure
```
j_github_sync/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── github_sync_server.py
│   ├── github_repository.py
│   └── github_sync_log.py
├── views/
│   ├── github_sync_server_views.xml
│   ├── github_repository_views.xml
│   ├── github_sync_log_views.xml
│   └── github_sync_menu.xml
└── security/
    ├── security.xml
    └── ir.model.access.csv
```

## Testing
Use demo mode to test all functionality without requiring external GitHub Sync Server connection. The demo mode provides realistic data for comprehensive testing of all features.