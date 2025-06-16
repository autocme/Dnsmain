#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PortainerStack(models.Model):
    _inherit = 'j_portainer.stack'

    def action_create_saas_client(self):
        """Create a SaaS client from this stack"""
        self.ensure_one()
        
        # Create SaaS client with stack as template
        # client_vals = {
        #     'sc_stack_id': self.id,
            # 'sc_server_id': self.server_id.id,
            # 'sc_environment_id': self.environment_id.id,
            # 'sc_template_content': self.file_content or self.content,
        # }
        
        # client = self.env['saas.client'].create(client_vals)
        
        return {
            'name': _('SaaS Client'),
            'type': 'ir.actions.act_window',
            'res_model': 'saas.client',
            # 'res_id': client.id,
            'view_mode': 'form',
            'target': 'new',
            'context':{
                'default_sc_stack_id':self.id,
            }
        }