from odoo import models


class IrCron(models.Model):
    _inherit = 'ir.cron'

    def trigger(self):
        self.check_access_rights('write')
        self._trigger()
        return True
