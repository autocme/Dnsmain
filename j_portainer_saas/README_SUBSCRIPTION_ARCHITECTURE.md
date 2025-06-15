# SaaS Subscription Template Architecture

## Overview

This document explains the new architecture for managing subscription templates through the `j_portainer_saas` module instead of directly modifying the base `subscription_oca` module.

## Problem Statement

Previously, subscription template modifications were being made directly in the `subscription_oca` module, which violates the principle of keeping base modules unchanged and makes maintenance difficult. All customizations should be handled through the SaaS module inheritance.

## New Architecture

### 1. Inheritance Pattern

The new architecture uses proper Odoo inheritance to extend base modules:

- **`j_portainer_saas/models/sale_subscription_template.py`**: Inherits `sale.subscription.template`
- **`j_portainer_saas/models/product_template.py`**: Inherits `product.template`
- **`j_portainer_saas/models/saas_package.py`**: Core SaaS package management

### 2. Data Flow

```
SaaS Package Creation → Subscription Template → Product Template
      ↓                        ↓                     ↓
   Manages pricing      Handles billing         Sellable item
   Resource limits      Recurring rules         List price sync
   Client lifecycle     Invoice generation      Name sync
```

### 3. Synchronization Logic

#### Context Flags (Prevent Infinite Loops)
- `from_saas_package`: Indicates template/product creation from SaaS package
- `skip_template_sync`: Prevents template sync loops
- `skip_product_sync`: Prevents product sync loops  
- `skip_saas_sync`: Prevents SaaS package sync loops

#### Bidirectional Sync
- **Package → Template**: Name, description, code synchronization
- **Package → Product**: Name and price synchronization
- **Product → Package**: Price and name changes flow back
- **Template → Package**: Linked through SaaS package relationship

## Key Components

### SaaS Package Model Extensions

#### New Methods:
- `create_subscription_template()`: Creates templates with proper context
- `sync_to_subscription_template()`: Manual synchronization trigger
- `action_view_subscription_template()`: Navigate to associated template

#### Enhanced Create Method:
```python
# Auto-creates subscription template with SaaS context
template = self.env['sale.subscription.template'].with_context(
    from_saas_package=True,
    saas_package_id=package.id,
    saas_package_name=package.pkg_name,
    saas_package_price=package.pkg_price or 0.0
).create(template_vals)
```

### Subscription Template Inheritance

#### New Fields:
- `saas_package_ids`: One2many relationship to SaaS packages
- `is_saas_template`: Boolean flag for SaaS-created templates
- `saas_package_count`: Computed count of linked packages

#### Enhanced Methods:
- `create()`: Handles SaaS package context and auto-creates products
- `write()`: Syncs changes back to SaaS packages
- `unlink()`: Cleans up package references

### Product Template Inheritance

#### New Fields:
- `is_saas_product`: Boolean flag for SaaS-created products
- `saas_package_id`: Many2one relationship to SaaS package

#### Enhanced Methods:
- `create()`: Marks products created from SaaS context
- `write()`: Syncs price/name changes back to SaaS packages

## Benefits

### 1. Clean Architecture
- Base modules remain untouched
- All SaaS customizations contained in one module
- Clear separation of concerns

### 2. Maintainability
- Easy to upgrade base modules without conflicts
- SaaS functionality can be disabled by uninstalling module
- Clear inheritance hierarchy

### 3. Data Integrity
- Bidirectional synchronization ensures consistency
- Context flags prevent infinite loops
- Comprehensive error handling and logging

### 4. Extensibility
- Easy to add new SaaS-specific fields and methods
- Can extend other models as needed
- Proper inheritance allows for future enhancements

## Migration Notes

### Removed from subscription_oca:
- Custom `create()` method with package logic
- Direct package integration code

### Added to j_portainer_saas:
- Complete inheritance models for subscription and product templates
- Comprehensive synchronization logic
- Context-aware creation methods

## Usage Examples

### Creating a SaaS Package:
```python
# This will auto-create subscription template and product
package = env['saas.package'].create({
    'pkg_name': 'Starter Package',
    'pkg_price': 29.99,
    'pkg_user_limit': 5,
    # ... other fields
})
# Template and product automatically created with proper linking
```

### Manual Template Creation:
```python
# Create template explicitly for SaaS package
template = package.create_subscription_template()
```

### Synchronization:
```python
# Manual sync if needed
package.sync_to_subscription_template()
```

## Context Usage

When creating templates or products for SaaS packages, always use the proper context:

```python
# For subscription templates
template = env['sale.subscription.template'].with_context(
    from_saas_package=True,
    saas_package_id=package.id,
    saas_package_name=package.pkg_name,
    saas_package_price=package.pkg_price
).create(vals)

# For products  
product = env['product.template'].with_context(
    from_saas_package=True,
    saas_package_id=package.id
).create(vals)
```

This architecture ensures all subscription template modifications are properly handled through the SaaS module while maintaining clean separation from base modules.