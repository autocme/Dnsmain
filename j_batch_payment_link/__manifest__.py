{
    'name': 'Batch Payment Link',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Generate single payment link for multiple invoices',
    'description': """
        Batch Payment Link Module
        =========================
        
        This module allows users to:
        - Select multiple invoices from tree view
        - Generate a single payment link for all selected invoices
        - Validate that all invoices belong to the same customer
        - Ensure all invoices are posted before generating payment link
        - Process batch payment and mark all invoices as paid
        - Track payment relationships with invoices via smart buttons
        
        Workflow:
        1. User selects multiple invoices from tree view
        2. Click "Batch Payment Generate Link" server action
        3. System validates same customer and posted status
        4. Payment link is generated with sum of all invoice amounts
        5. Customer pays through the link
        6. All selected invoices are automatically paid
        7. Payment record shows linked invoices in smart button
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