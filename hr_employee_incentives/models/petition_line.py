from odoo import fields, models


class PetitionLine(models.Model):
    _name = 'hr.petition.line'
    _description = 'أسطر الالتماس'
    _order = 'sequence asc, id asc'

    petition_id = fields.Many2one('hr.petition', string='الالتماس', ondelete='cascade', required=True)
    sequence = fields.Integer(string='التسلسل', default=10)
    name = fields.Char(string='البيان', required=True)
    date = fields.Date(string='التاريخ', default=fields.Date.context_today)
    amount = fields.Float(string='القيمة')
    notes = fields.Text(string='ملاحظات')
