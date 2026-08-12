from odoo import models, api, fields

class HospitalInvoiceLine(models.Model):
    _name = 'hospital.invoice.line'
    _description = 'Hospital Invoice Line'

    invoice_id = fields.Many2one('hospital.invoice', string='Invoice', ondelete='cascade')
    name = fields.Char(string='Service / Description', required=True)
    quantity = fields.Float(string='Quantity / Days', default=1.0)
    price_unit = fields.Float(string='Unit Price', default=0.0)
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_price_subtotal', store=True)

    @api.depends('quantity', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit