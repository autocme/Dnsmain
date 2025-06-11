# Volume-Container Relationship Fix

## Problem
The `container_volume_ids` field in volumes was not showing connected containers because the container sync process wasn't properly linking container-volume relationships to the actual volume records.

## Root Cause
In the `_smart_sync_volumes` method of `portainer_container.py`, the system was only storing the source path in the `name` field but not establishing the Many2one relationship to the actual volume record through the `volume_id` field.

## Solution
Enhanced the `_smart_sync_volumes` method to:

1. **Detect mount types**: Distinguish between named volumes and bind mounts using the `Type` field
2. **Link named volumes**: For `type='volume'` mounts, search for the corresponding volume record and establish the relationship
3. **Store proper data**: Use volume name instead of source path for named volumes
4. **Update comparison logic**: Enhanced the sync comparison to handle `volume_id` field changes
5. **Handle edge cases**: Properly handle cases where `volume_id` might be False/None

## Key Changes

### 1. Enhanced Volume Data Building
```python
# For named volumes, try to link to the volume record
if mount_type == 'volume' and mount_name:
    volume_record = self.env['j_portainer.volume'].search([
        ('server_id', '=', self.server_id.id),
        ('environment_id', '=', self.environment_id.id),
        ('name', '=', mount_name)
    ], limit=1)
    
    if volume_record:
        volume_data['volume_id'] = volume_record.id
        volume_data['name'] = mount_name
```

### 2. Improved Sync Comparison
```python
# Check volume_id relationship changes
expected_volume_id = expected_volume.get('volume_id')
current_volume_id = current_volume.volume_id.id if current_volume.volume_id else False
if current_volume_id != expected_volume_id:
    update_data['volume_id'] = expected_volume_id
    needs_update = True
```

## Result
- Container-volume relationships now properly populate the `container_volume_ids` field
- Volume forms show connected containers in the "Containers" tab
- Volume tree view displays correct container counts
- Color coding works properly (green for volumes in use, gray for unused)

## Sync Order
The fix works because volumes are synced before containers in `sync_all()`:
1. `sync_volumes()` - Creates volume records
2. `sync_containers()` - Links containers to existing volume records

This ensures volume records exist when containers try to reference them.