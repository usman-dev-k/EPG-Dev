{
    'name': 'SaaS Training',
    'version': '18.0.1.0',
    'category': 'Extra Tools',
    'summary': 'Basic training module with YouTube links',
    'author': 'Arcthane',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/training_video_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
