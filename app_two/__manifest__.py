{
    'name': 'test_practice',
    'version': '18.0.1.0.0',
    'category': 'Healthcare',
    'depends': ['base','mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/patient_view.xml',
        'views/doctor_view.xml',
        'views/invoice_view.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': True,
}
