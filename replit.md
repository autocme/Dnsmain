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

## July 6, 2025 - Package Model Architectural Refactoring

- **MAJOR ARCHITECTURE CHANGE**: Removed single `pkg_price` field from package model
- **Added separate pricing fields**: `pkg_mon_price` and `pkg_yea_price` for dedicated monthly/yearly pricing
- **Dual subscription template system**: Added `pkg_mon_subs_template_id` and `pkg_yea_subs_template_id` fields
- **Enhanced SaaS client model**: Added `sc_subscription_period` selection field (monthly/yearly) to determine which template to use
- **Automatic template creation**: Updated package creation process to auto-generate both monthly and yearly subscription templates
- **Smart template selection**: Client subscription creation now selects appropriate template based on subscription period
- **Updated form views**: Modified package form to display monthly/yearly pricing in organized rows with clear labeling
- **Controller updates**: Modified web controller to use new price fields (`pkg_mon_price`, `pkg_yea_price`) instead of calculated discounts
- **JavaScript enhancements**: Updated pricing snippets to handle null pricing values gracefully
- **Template inheritance**: Updated sale subscription template inheritance to track both monthly and yearly package relationships
- **Field cleanup**: Removed all references to deprecated fields (`pkg_price`, `pkg_subscription_period`, `pkg_subscription_template_id`)
- **View updates**: Updated tree, form, kanban, and search views to use new dual-pricing structure
- **Product synchronization**: Enhanced product template inheritance to work with new dual pricing system
- **Template cleanup**: Updated subscription template unlink method to properly handle new package relationships
- **Subscription template fixes**: Fixed template creation to use correct billing types (monthly vs yearly)
- **Product creation enhancement**: Updated product creation to include billing period in names and proper field mapping
- **Client view enhancements**: Added sc_subscription_period field to all client views (tree, form, kanban, search)
- **Template linking**: Improved product-template linking process with proper field validation

## Previous Features (Pre-July 6, 2025)

- Created comprehensive j_portainer_saas_web module with modern pricing snippet for website integration
- Implemented Monthly/Yearly billing toggle with dynamic price calculations and smooth animations
- Added extensive dynamic styling options allowing users to customize colors, layouts, typography, and effects
- Created controller for package data fetching with automatic yearly discount calculations (10% default)
- Built responsive pricing cards with conditional free trial button display based on pkg_has_free_trial field
- Integrated snippet options panel with predefined color schemes and full customization capabilities
- Added general settings section for j_portainer_saas module with free trial configuration
- Created settings model with free_trial_interval_days field (default: 30 days) 
- Added pkg_has_free_trial checkbox to package model for enabling free trials per package
- Created settings view interface accessible through Settings > General Settings
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
- Replaced column options with Layout option similar to Comparisons snippet (1, 2, 3, 4, 6 columns)
- Added comprehensive layout system with responsive breakpoints and proper Bootstrap classes
- Set default layout to 3 columns per row for optimal pricing display
- Enhanced package visibility controls with real-time checkbox interface in snippet options
- Implemented complete package purchase functionality with user authentication
- Added purchase endpoint (/saas/package/purchase) requiring user login with auth='user'
- Created SaaS client records with draft status when users purchase packages
- Built comprehensive JavaScript purchase handlers with loading states and error handling
- Added success/error message system with auto-dismiss and proper positioning
- Integrated billing cycle detection (monthly/yearly) from pricing toggle
- Added test redirect to Google after successful purchase (pending final URL implementation)
- Implemented login requirement checks with automatic redirect to /web/login

# Changelog

- June 24, 2025. Initial setup

# User Preferences

Preferred communication style: Simple, everyday language.