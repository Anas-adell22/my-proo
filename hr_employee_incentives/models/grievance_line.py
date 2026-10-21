from odoo import fields, models


class GrievanceLine(models.Model):
    _name = 'hr.grievance.line'
    _description = 'أسطر التظلم'
    _order = 'sequence asc, id asc'

    grievance_id = fields.Many2one('hr.grievance', string='التظلم', ondelete='cascade', required=True)
    sequence = fields.Integer(string='التسلسل', default=10)
    name = fields.Char(string='البيان', required=True)
    date = fields.Date(string='التاريخ', default=fields.Date.context_today)
    amount = fields.Float(string='القيمة')
    notes = fields.Text(string='ملاحظات')
