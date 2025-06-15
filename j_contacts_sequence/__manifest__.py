{
    'name': 'Contacts Sequence',
    'version': '17.0.1.0.0',
    'category': 'Contacts',
    'summary': 'Add sequence numbering to contacts',
    'description': 'Add automatic sequence numbering to partners using format C0000001',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['contacts'],
    'data': [
        'data/sequence_data.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}