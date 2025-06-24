# Overview

This is an Odoo 17.0 development environment with custom subscription and job queue modules. The project contains two main custom addons:

1. **subscription_oca** - A subscription management module for generating recurring invoices
2. **queue_job** - A job queue system for handling asynchronous tasks

The environment is configured to run Odoo with PostgreSQL integration and includes all necessary dependencies for both modules.

# System Architecture

## Frontend Architecture
- **Web Interface**: Odoo's standard web interface with custom views for subscription and job management
- **Views**: XML-based views using Odoo's QWeb templating engine
- **JavaScript Components**: Custom JavaScript components for job visualization (vis-network graphs)
- **CSS/SCSS**: Custom styling for job queue visualization components

## Backend Architecture
- **Framework**: Odoo 17.0 (Python-based ERP framework)
- **ORM**: Odoo's built-in ORM for database operations
- **Models**: Custom Python models extending Odoo's base models
- **Business Logic**: Python methods implementing subscription and job queue functionality
- **API**: Odoo's XML-RPC and JSON-RPC APIs for external integration

## Database Layer
- **Primary Database**: PostgreSQL (configured but not explicitly set up)
- **ORM**: Odoo ORM handling database operations
- **Migrations**: Odoo's built-in migration system through module updates
- **Triggers**: PostgreSQL triggers for job queue notifications

# Key Components

## Subscription Management (subscription_oca)
- **Models**: 
  - `sale.subscription` - Main subscription records
  - `sale.subscription.template` - Subscription templates
  - `sale.subscription.line` - Subscription line items
  - `sale.subscription.stage` - Subscription lifecycle stages
- **Features**:
  - Recurring invoice generation
  - Subscription templates with configurable intervals
  - Integration with sales orders and products
  - Stage-based subscription lifecycle management
  - Automated cron job for subscription processing

## Job Queue System (queue_job)
- **Models**:
  - `queue.job` - Job records and execution tracking
  - `queue.job.channel` - Job channels for organizing work
  - `queue.job.function` - Job function configurations
- **Features**:
  - Asynchronous job execution
  - Job retry mechanisms with configurable patterns
  - Channel-based job organization
  - Job dependency management
  - Real-time job monitoring with PostgreSQL notifications

## Integration Points
- **Sales Integration**: Subscription products can be sold through standard sales orders
- **Accounting Integration**: Automatic invoice generation from subscriptions
- **Partner Management**: Customer subscription tracking
- **Email Integration**: Automated email notifications for invoices

# Data Flow

## Subscription Flow
1. Create subscription template with billing frequency
2. Create subscription from template or sale order
3. Cron job processes active subscriptions
4. Generate invoices/orders based on template configuration
5. Update subscription dates and status

## Job Queue Flow
1. Method calls are delayed using `with_delay()`
2. Jobs are stored in PostgreSQL with metadata
3. Jobrunner processes jobs from channels
4. Jobs execute in separate transactions
5. Results and errors are tracked in job records

# External Dependencies

## Python Dependencies
- **Core Odoo**: All standard Odoo 17.0 dependencies
- **Subscription Module**: 
  - Standard Odoo modules (sale_management, account)
- **Job Queue Module**:
  - `requests` library for HTTP operations
  - `base_sparse_field` for field handling
- **System Dependencies**: PostgreSQL, various image processing libraries

## JavaScript Dependencies
- **vis-network**: For job dependency graph visualization
- **Standard Odoo**: Web framework dependencies

# Deployment Strategy

## Development Environment
- **Container**: Nix-based development environment
- **Server**: Python HTTP server on port 5000
- **Database**: PostgreSQL (to be configured)
- **Jobrunner**: Integrated with Odoo server process

## Production Considerations
- **Workers**: Requires multi-worker setup for job queue functionality
- **Database**: PostgreSQL with proper indexing for job queue performance
- **Monitoring**: Job queue provides built-in monitoring views
- **Scaling**: Channel-based job distribution for load balancing

## Configuration
- **Environment Variables**: Support for job queue configuration
- **Odoo Config**: Server-wide module loading configuration
- **Database Setup**: Automatic trigger creation for job notifications

# Recent Changes

- Added automatic payment processing for batch payments when transactions are confirmed
- Implemented transaction state tracking with amount validation before processing
- Auto-posting of draft invoices and payment reconciliation using existing transaction payments
- Updated batch payment model to store multiple payment transactions using Many2many field
- Changed payment_transaction_id to payment_transaction_ids with compute method for reference matching
- Added payment transaction inheritance model with batch_payment_id field
- Updated views and action methods to handle multiple transaction records
- Modified subdomain creation logic in SaaS client model to prioritize public_url over URL
- Added IP extraction from server URLs using regex pattern for IPv4 addresses
- Implemented fallback hierarchy: public_url → server IP extraction → deployment environment URL
- Added comprehensive search view to SaaS client model with filters for status, stack status, and resource availability
- Search view includes grouping options by partner, package, template, and dates

# Changelog

- June 24, 2025. Initial setup

# User Preferences

Preferred communication style: Simple, everyday language.