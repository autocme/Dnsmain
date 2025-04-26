import logging
from odoo import models, api

_logger = logging.getLogger(__name__)

class SafeReadMixin(models.AbstractModel):
    """
    Mixin that overrides the _read_format method to handle '_unknown' objects
    that don't have an id attribute during creation.
    
    This is needed to handle issues when creating records with Many2one fields.
    """
    _name = 'safe.read.mixin'
    _description = 'Safe Read Mixin'
    
    @api.model
    def _is_mail_thread_enabled(self):
        """Check if mail.thread is installed and enabled"""
        return 'mail.thread' in self.env and hasattr(self.env['mail.thread'], '_read_format')
        
    @api.model
    def _get_original_read_format(self):
        """Get the original _read_format method to call it when possible"""
        if self._is_mail_thread_enabled():
            return self.env['mail.thread']._read_format
        return super(SafeReadMixin, self)._read_format
        
    def _read_format(self, fnames):
        """
        Override _read_format to handle '_unknown' objects that lack an id attribute
        
        This happens during record creation when trying to read Many2one fields.
        """
        original_read_format = self._get_original_read_format()
        
        records = self
        result = []
        
        for record in records:
            try:
                # Try original method
                record_result = original_read_format(record, fnames)
                result.append(record_result)
            except AttributeError as e:
                if "'_unknown' object has no attribute 'id'" in str(e):
                    # Handle the specific error
                    _logger.warning("Handling '_unknown' object with no id for %s", record)
                    vals = {'id': False if not hasattr(record, 'id') else record.id}
                    
                    # Set False for all fields that might cause errors
                    for name in fnames:
                        try:
                            field = record._fields[name]
                            # For Many2one fields, use False if we get an '_unknown' object
                            if field.type == 'many2one' and hasattr(record, name):
                                value = record[name]
                                if not hasattr(value, 'id'):
                                    vals[name] = False
                                else:
                                    vals[name] = value.id
                            else:
                                # For other fields, try to convert or use False
                                try:
                                    value = record[name]
                                    if hasattr(field, 'convert_to_read'):
                                        vals[name] = field.convert_to_read(value, record, use_display_name=False)
                                    else:
                                        vals[name] = value
                                except Exception:
                                    vals[name] = False
                        except Exception as field_e:
                            _logger.warning("Error handling field %s: %s", name, field_e)
                            vals[name] = False
                            
                    result.append(vals)
                else:
                    # If not the specific error we're handling, re-raise
                    raise
        
        return result if len(records) > 1 else result[0] if result else {}