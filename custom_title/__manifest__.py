{
    'name': 'Custom Browser Title',
    'version': '18.0.1.0.0',
    'summary': 'Removes Odoo from browser tab title',
    'category': 'Customization',
    'depends': ['web'],
    'data': [
        'views/webclient_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_title/static/src/js/title_override.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
