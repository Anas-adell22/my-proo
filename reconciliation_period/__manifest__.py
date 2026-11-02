{
    'name': 'Reconciliation Period',
    'version': '18.0.1.0.0',
    'depends': ['base', 'mail', 'account', 'sales_team'],
    'data': [
        'security/ir.model.access.csv',
        'data/period_option_data.xml',
        'report/report_salesperson.xml',
        'views/period_views.xml',
    ],
    'license': 'LGPL-3',
}
