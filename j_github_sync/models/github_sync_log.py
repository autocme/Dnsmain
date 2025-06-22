#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class GitHubSyncLog(models.Model):
    """
    GitHub Sync Log Model
    
    This model stores logs retrieved from the GitHub Sync Server.
    """
    
    _name = 'github.sync.log'
    _description = 'GitHub Sync Log'
    _order = 'gsl_timestamp desc'
    _rec_name = 'gsl_message'

    # ========================================================================
    # BASIC FIELDS
    # ========================================================================
    
    gsl_timestamp = fields.Datetime(
        string='Timestamp',
        required=True,
        help='When the log entry was created'
    )
    
    gsl_level = fields.Selection([
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical')
    ], string='Level', required=True, default='info')
    
    gsl_status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('pending', 'Pending'),
        ('failed', 'Failed')
    ], string='Status')
    
    gsl_operation_type = fields.Selection([
        ('pull', 'Pull'),
        ('clone', 'Clone'),
        ('restart', 'Restart'),
        ('webhook', 'Webhook'),
        ('sync', 'Sync'),
        ('deploy', 'Deploy'),
        ('backup', 'Backup'),
        ('other', 'Other')
    ], string='Operation Type')
    
    gsl_message = fields.Text(
        string='Message',
        required=True
    )
    
    gsl_operation = fields.Char(
        string='Operation',
        help='Operation identifier'
    )
    
    gsl_repository = fields.Char(
        string='Repository',
        help='Repository name'
    )
    
    gsl_details = fields.Text(
        string='Details',
        help='Additional operation details'
    )
    
    gsl_external_id = fields.Char(
        string='External ID',
        help='External log ID from GitHub Sync Server'
    )
    
    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    
    gsl_server_id = fields.Many2one(
        'github.sync.server',
        string='GitHub Sync Server',
        required=True,
        ondelete='cascade',
        help='GitHub Sync Server that generated this log'
    )
    
    gsl_company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    _sql_constraints = [
        ('unique_external_id_server', 'UNIQUE(gsl_external_id, gsl_server_id)', 
         'Log external ID must be unique per server.'),
    ]