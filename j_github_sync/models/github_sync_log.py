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
    _order = 'gsl_time desc'
    _rec_name = 'gsl_message'

    # ========================================================================
    # BASIC FIELDS
    # ========================================================================
    
    gsl_time = fields.Datetime(
        string='Time',
        required=True,
        help='When the log entry was created'
    )
    
    gsl_operation = fields.Selection([
        ('pull', 'Pull'),
        ('clone', 'Clone'),
        ('restart', 'Restart'),
        ('webhook', 'Webhook')
    ], string='Operation', required=True,
       help='Type of operation that generated this log')
    
    gsl_status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('pending', 'Pending'),
        ('in_progress', 'In Progress')
    ], string='Status', required=True,
       help='Status of the operation')
    
    gsl_message = fields.Text(
        string='Message',
        required=True,
        help='Log message content'
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