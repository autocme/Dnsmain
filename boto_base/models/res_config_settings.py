# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (C) 2023 JAAH

import boto3
from odoo import api, fields, models, _

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # AWS Credentials Settings
    aws_manage_credentials = fields.Boolean(string='AWS Integration', 
                                           config_parameter='boto_base.aws_manage_credentials')
    aws_default_region = fields.Char(string='Default AWS Region', 
                                    config_parameter='boto_base.aws_default_region',
                                    default='us-east-1')
    aws_credentials_count = fields.Integer(string='Credentials Count', compute='_compute_aws_credentials_count')
    aws_default_credentials_id = fields.Many2one('aws.credentials', string='Default AWS Credentials',
                                                compute='_compute_aws_default_credentials',
                                                readonly=True)
    
    @api.depends('aws_manage_credentials')
    def _compute_aws_credentials_count(self):
        """Compute the number of saved AWS credentials"""
        for record in self:
            if record.aws_manage_credentials:
                record.aws_credentials_count = self.env['aws.credentials'].search_count([])
            else:
                record.aws_credentials_count = 0
    
    @api.depends('aws_manage_credentials')
    def _compute_aws_default_credentials(self):
        """Get the default AWS credentials"""
        for record in self:
            if record.aws_manage_credentials:
                record.aws_default_credentials_id = self.env['aws.credentials'].get_default_credentials()
            else:
                record.aws_default_credentials_id = False
    
    def action_aws_credentials(self):
        """Open the AWS credentials list view"""
        self.ensure_one()
        return {
            'name': _('AWS Credentials'),
            'type': 'ir.actions.act_window',
            'res_model': 'aws.credentials',
            'view_mode': 'tree,form',
        }
    
    def action_create_aws_credentials(self):
        """
        Open a form to create new AWS credentials
        """
        self.ensure_one()
        return {
            'name': _('Create AWS Credentials'),
            'type': 'ir.actions.act_window',
            'res_model': 'aws.credentials',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_aws_default_region': self.aws_default_region,
            },
        }
    
    def test_aws_connectivity(self):
        """
        Test AWS connectivity with the default credentials
        """
        self.ensure_one()
        
        if not self.aws_default_credentials_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('No default AWS credentials found. Please set default credentials.'),
                    'sticky': True,
                    'type': 'danger',
                }
            }
            
        return self.aws_default_credentials_id.test_credentials()