# Portainer Integration for Odoo 17

This module provides integration with Portainer Community Edition 2.27.4 LTS, allowing you to manage Docker resources through Portainer's API directly from Odoo.

## Features

* **Server Management**: Connect to multiple Portainer servers using API key authentication
* **Environment Sync**: Synchronize all environments (endpoints) from Portainer
* **Container Management**: View, start, stop, restart, and remove containers
* **Image Management**: Pull, inspect, and remove Docker images
* **Volume Management**: View and manage Docker volumes
* **Network Management**: View and manage Docker networks
* **Template Management**: Sync and deploy standard application templates
* **Custom Template Management**: Create, sync, and deploy custom templates
* **Stack Management**: Deploy and manage Docker Compose stacks
* **Bidirectional Sync**: Changes in Odoo can be pushed to Portainer (custom templates)

## Technical Notes

* Exclusively uses Portainer v2 API endpoints for full compatibility with Portainer CE 2.9.0+ and 2.27.4 LTS
* All legacy v1 API endpoints have been completely removed
* Template ID fields use Char type instead of Integer for better compatibility and flexibility
* Requires Server and Environment fields for custom templates to ensure proper Portainer integration
* Enhanced error handling with graceful record creation even when API calls fail
* "Manual Template ID" feature available for linking manually created Portainer templates

## Installation

1. Install this module using the standard Odoo module installation process
2. Configure at least one Portainer server with a valid API key
3. Use the sync wizard to synchronize resources from Portainer

## Configuration

To configure a Portainer server:

1. Go to Portainer > Configuration > Servers
2. Create a new server with:
   - Name: A descriptive name for the server
   - URL: The complete URL including protocol and port (e.g., https://portainer.example.com:9443)
   - API Key: A valid API key created in Portainer (Settings > API)
   - Verify SSL: Enable/disable SSL certificate verification

## Usage

* Use the sync button on the server form to sync all resources
* Individual sync buttons are available for each resource type
* Create custom templates in Odoo and they will automatically sync to Portainer
* Deploy templates and stacks directly from Odoo

## Requirements

* Portainer Community Edition 2.9.0+ (optimized for 2.27.4 LTS)
* Valid API key with appropriate permissions
* Network connectivity between Odoo and Portainer