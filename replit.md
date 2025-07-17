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
- **Infinite loop fix**: Removed product-to-package name synchronization to prevent infinite loops during product name changes
- **Template synchronization**: Enhanced product-to-template name synchronization with proper context flags to prevent loops
- **Client template computation**: Added automatic template creation trigger in client compute method to ensure templates exist
- **Debug logging**: Added comprehensive logging for template selection and creation to troubleshoot selection issues
- **Smart price synchronization**: Redesigned product-to-package price sync to use subscription template relationships for accurate billing period detection
- **Template-based price routing**: Product price changes now check template's recurring_rule_type to determine correct package price field (monthly/yearly)
- **Conflict resolution**: Eliminated price sync conflicts by using subscription template as the authoritative source for billing period determination
- **Website billing toggle fix**: Corrected inverted billing toggle logic where checked state now properly maps to yearly (was incorrectly mapping to monthly)
- **Purchase endpoint correction**: Updated JavaScript to call correct /saas/package/purchase endpoint instead of placeholder /saas/package/select
- **Enhanced purchase flow**: Added proper login redirect handling and success/error messaging for website purchases
- **Purchase request validation**: Added billing cycle parameter validation and comprehensive logging for debugging website purchases
- **Template selection debugging**: Added detailed logging throughout purchase flow to track billing cycle selection and SaaS client creation
- **pricing_snippet_simple.js billing fix**: Fixed inconsistent billing toggle logic where setupBillingToggle used checked=monthly but purchase used checked=yearly
- **Removed unused pricing_snippet.js**: Eliminated unused JavaScript file to prevent confusion and focus on pricing_snippet_simple.js
- **Enhanced purchase request format**: Removed free_trial parameter from purchase request to match controller expectations
- **Added client-side debugging**: Added console logging to track billing cycle selection during purchase flow
- **Package Features Model**: Added new saas.package.features model with one2many relation to packages for managing feature lists
- **Field Rename pf_name**: Renamed pf_feature_text field to pf_name across all model, view, and controller files
- **Website Publishing Control**: Added pkg_publish_website boolean field to control which packages appear on website
- **Dynamic Package Features**: Updated website controller to use actual package features instead of static hardcoded values
- **Enhanced Package Form**: Added Package Features as first page in form view with inline editable tree for feature management
- **Feature Priority System**: Implemented feature retrieval hierarchy (Package Features > Description > Template Variables > Default)
- **Security Access Rules**: Added proper access control for package features model
- **Model Integration**: Complete integration of package features with existing package model and website display
- **Subscription Template Activation Control**: Added pkg_monthly_active and pkg_yearly_active boolean fields to control template generation
- **Strict Website Filtering**: Website only displays packages with both monthly and yearly subscription templates active
- **Template Generation Logic**: Updated template creation to respect activation flags - templates only created when corresponding activation field is True
- **Enhanced Package Form Layout**: Added activation checkboxes inline with pricing fields in form view for easy template control
- **Authentication Error Handling**: Fixed JavaScript purchase flow to properly handle authentication errors for public users
- **Login Redirect Enhancement**: Added proper authentication failure detection with automatic redirect to /web/login for non-authenticated users
- **DOM Error Prevention**: Enhanced error handling to prevent JavaScript DOM manipulation errors when users aren't logged in
- **Seamless Purchase Flow**: Added session storage to preserve purchase details during login redirect
- **Automatic Purchase Completion**: Implemented automatic purchase completion after user logs in, eliminating need to re-click purchase button
- **Error Message Protection**: Added try-catch blocks around error display functions to prevent recursive innerHTML errors
- **Dynamic Package Filtering**: Implemented toggle-based package visibility using activation fields (pkg_monthly_active/pkg_yearly_active)
- **Flexible Website Display**: Website now shows packages based on toggle state - monthly toggle shows monthly-active packages, yearly toggle shows yearly-active packages
- **Backend Filter Optimization**: Removed strict monthly AND yearly requirement, now shows all published packages with frontend filtering
- **Toggle Logic Fix**: Corrected inverted toggle logic - checked state now properly represents monthly, unchecked represents yearly
- **Price Display Correction**: Fixed price display to show correct monthly/yearly prices and periods based on toggle state
- **Toggle Style Enhancement**: Updated toggle styling to match Odoo official website - toggle now appears "checked" for both yearly and monthly states
- **Toggle Position Adjustment**: Configured toggle circle positioning - yearly shows circle on left, monthly shows circle on right

## July 9, 2025 - SaaS Client Enhancements

- **Smart Button for Invoices**: Added sc_invoice_count computed field and action_view_invoices method to display subscription-related invoices
- **Free Trial Boolean Field**: Added sc_is_free_trial field to SaaS client model with conditional visibility based on package free trial settings
- **Package Free Trial Related Field**: Added sc_package_has_free_trial related field to properly access package free trial status in views
- **Free Trial Subscription Logic**: Modified subscription creation to calculate start date based on free trial status and settings interval
- **Subscription Start Date Fix**: Fixed subscription creation workflow to start subscription first, then apply custom start date to prevent base code from resetting start date to today
- **Subscription Activation**: Moved action_start_subscription call to handle stage setting automatically instead of manual stage assignment
- **First Invoice Generation**: Added automatic first invoice generation for paid subscriptions (non-free trial) during client creation using manual_invoice method
- **Package Form Field Repositioning**: Repositioned pkg_monthly_active and pkg_yearly_active fields to appear first in pricing rows
- **Conditional Field Visibility**: Updated to Odoo 17.0 syntax using invisible attribute instead of attrs for field visibility control
- **Smart Button Integration**: Added invoices smart button to client form view with proper visibility and navigation
- **Website Free Trial Integration**: Updated website purchase flow to detect free trial button clicks and pass is_free_trial parameter to SaaS client creation
- **Free Trial Validation**: Added server-side validation to ensure free trial requests are only processed for packages with pkg_has_free_trial enabled
- **Purchase Flow Enhancement**: Modified JavaScript to distinguish between regular purchase and free trial button clicks, passing appropriate parameters to backend
- **Button Click Debugging**: Enhanced event delegation to properly handle buttons with complex HTML structure (icons, spans) using closest() method
- **Loading State Fix**: Updated loading state functions to preserve button HTML structure instead of stripping it with textContent
- **Enhanced Debugging**: Added comprehensive console logging for button clicks, purchase requests, and error handling
- **Purchase Confirmation Flow**: Complete redesign of purchase process with dedicated confirmation page (/saas/purchase/confirm)
- **Step Progress Indicator**: Added elegant 3-step progress bar (Package Selection → Payment/Trial → Setup) matching Odoo's design
- **Legal Agreement Integration**: Added subscription agreement and privacy policy acceptance requirement
- **Elegant Loading States**: Interactive loading screen during client creation with animated progress bars
- **Success Screen**: Professional completion page with checklist and "All done!" message
- **Responsive Confirmation Page**: Modern, classy design with unique CSS classes to avoid conflicts
- **Free Trial Auto-Deployment**: Free trial clients are automatically deployed after creation, paid clients require manual deployment
- **Fixed Free Trial Parameter Flow**: Resolved issue where is_free_trial parameter wasn't being passed correctly to client creation
- **Enhanced Paid Package Flow**: Added subscription creation notice and invoice generation for paid packages
- **Invoice Portal Integration**: Paid packages now show invoice portal link for payment processing
- **Auto-Deployment for Paid Clients**: Added automatic deployment trigger when subscription invoices are paid
- **Subdomain Redirect**: Success screen now redirects to client's full domain instead of dashboard
- **Account Move Extension**: Added invoice payment monitoring to trigger client deployment automatically
- **Fixed Free Trial Parameter Flow**: Resolved Python boolean to string conversion issue in QWeb templates where `True` was being converted to `'True'` instead of `'true'`, causing JavaScript boolean parsing to fail
- **URL Redirection Fix**: Corrected success screen redirect to use clean domain URLs without server prefix (e.g., `https://33.jaah.it` instead of `http://192.168.1.54:8070/saas/purchase/33.jaah.it`)
- **Removed Duplicate Invoice Creation**: Eliminated duplicate invoice generation in controller, letting base module handle all invoice creation automatically
- **Enhanced Invoice Portal Integration**: Controller now retrieves existing invoices from subscriptions instead of creating new ones
- **Clean Domain URL Handling**: Added proper URL parsing and cleaning for client domain redirects in both controller and JavaScript
- **Debug Logging Enhancement**: Added comprehensive logging throughout purchase flow to track parameter passing and client creation

## July 17, 2025 - Ecommerce-Style Checkout Implementation

- **Complete Ecommerce Layout**: Transformed purchase confirmation page to exactly match Odoo's standard ecommerce "Confirm order" page
- **Breadcrumb Navigation**: Added Review Order → Shipping → Payment breadcrumb navigation matching ecommerce patterns
- **Two-Column Layout**: Implemented left column for payment methods and right sidebar for order summary
- **Payment Method Selection**: Added proper payment method selection with radio buttons and provider logos
- **Order Summary Sidebar**: Created detailed order summary with item details, pricing breakdown, subtotal, taxes, and total
- **Discount Code Integration**: Added discount code input field with "Apply" button in order summary
- **Pay Now Button**: Replaced custom buttons with standard "Pay now" button matching ecommerce styling
- **Back to Packages Link**: Added navigation link to return to package selection
- **Clean Interface**: Removed unnecessary elements like billing address section to focus on SaaS-specific needs
- **Responsive Design**: Maintained full mobile responsiveness while following ecommerce patterns
- **Native Payment Form Integration**: Replaced custom payment UI with Odoo's built-in `payment.form` template using `<t t-call="payment.form"/>`
- **CSS Cleanup**: Removed all conflicting custom Bootstrap styling, kept only minimal CSS for loading screens and basic integration
- **JavaScript Simplification**: Removed custom payment processing code, kept only free trial flow handling since payments are now handled by Odoo's payment module
- **Controller Updates**: Updated controller to pass correct variables for payment form template (providers, reference, amount, currency, etc.)
- **Template Approach**: Leveraged existing Odoo payment templates instead of creating custom implementation from scratch

## July 15, 2025 - Payment-First Implementation for Paid Packages (Odoo 17 Compatible)

- **Template UI Cleanup**: Removed "What's included" section and simplified subscription notes in purchase confirmation template
- **Modern Payment Integration**: Added elegant payment section with Odoo payment provider support for paid packages (Odoo 17 uses payment.provider instead of payment.acquirer)
- **Payment Method Selection**: Implemented professional payment provider selection with grid layout and hover effects
- **Dual Flow System**: Free trials use existing flow (Start Now → Direct creation), paid packages use payment-first flow (Pay Now → Payment processing → Client creation)
- **Payment Transaction Extension**: Extended payment.transaction model with custom SaaS fields (x_saas_package_id, x_saas_billing_cycle, x_saas_user_id)
- **Automatic Client Creation**: SaaS clients are automatically created after successful payment completion
- **Payment-Invoice Linking**: Payment transactions are properly linked to subscription invoices for accurate accounting
- **Auto-Deployment**: Paid clients are automatically deployed after successful payment processing
- **Direct Instance Redirect**: After payment success, users are redirected directly to their SaaS instance subdomain
- **Enhanced Error Handling**: Added professional error pages and comprehensive payment flow error handling
- **Unique CSS Classes**: All styling uses unique saas_* prefixed classes to avoid conflicts with base Odoo styles
- **Payment Form Integration**: Integrated with Odoo's standard payment form rendering for seamless provider processing
- **Transaction State Management**: Proper handling of payment states (done, pending, failed) with appropriate user feedback
- **Payment Module Fallback**: Added graceful fallback to regular purchase flow when payment module is not available or enabled
- **Conditional Payment Processing**: Payment functionality only loads when payment.provider model is available in the system (Odoo 17 uses payment.provider instead of payment.acquirer)
- **Odoo 17 Compatibility**: Full compatibility with Odoo 17's payment.provider system, with fallback support for older payment.acquirer versions
- **Flexible Template Logic**: Templates adapt to show payment section only when payment providers are available
- **Error-Resilient Architecture**: System continues to work normally even without payment module dependency

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