# -*- coding: utf-8 -*-

from odoo import models, fields


class PortainerResourceType(models.Model):
    _name = 'j_portainer.resource.type'
    _description = 'Portainer Resource Type'
    _order = 'name'

    name = fields.Char('Resource Type', required=True, help="Display name of the resource type")
    sync_method = fields.Char('Sync Method', required=True, help="Method name to call for synchronizing this resource type")

    def name_get(self):
        """Custom name display"""
        result = []
        for record in self:
            result.append((record.id, record.name))
        return result