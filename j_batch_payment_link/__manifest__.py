{
    'name': 'Batch Payment Link',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Generate single payment link for multiple invoices',
    'description': """
        Simple batch payment link generation for multiple invoices.
        
        Features:
        - Select multiple customer invoices
        - Generate single payment link with total amount
        - Validates same customer, posted status, and currency
        - Uses standard Odoo payment system
        
        Usage: Select invoices → "Batch Payment Generate Link" → Payment wizard opens with total amount
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['account'],
    'data': [
        'data/server_actions.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}