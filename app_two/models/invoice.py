from odoo import api, fields, models

class HospitalInvoice(models.Model):
    _name = 'hospital.invoice'
    _description = 'Hospital Invoice'

    patient_id = fields.Many2one('hospital.patient', string='Patient', required=True, ondelete='cascade')
    patient_name = fields.Char(string='Patient Name', related='patient_id.name', store=True, readonly=True)
    patient_phone = fields.Char(string='Patient Phone', related='patient_id.phone', store=True, readonly=True)
    patient_national_id = fields.Char(string='National ID', related='patient_id.national_id', store=True, readonly=True)
    admission_date = fields.Date(string='Admission Date')
    discharge_date = fields.Date(string='Discharge Date')
    number_of_days = fields.Float(string='Number of Days', compute='_compute_num_of_days', store=True)
    room_price_per_day = fields.Float(string="Room fee per day", default=0.0)
    room_total_amount = fields.Float(string='Room total Amount', compute='_compute_room_total_amount', store=True)
    line_ids = fields.One2many('hospital.invoice.line', 'invoice_id', string='Invoice lines')
    total_amount = fields.Float(string='Total Amount', compute='_compute_total_amount', store=True)

    @api.onchange('patient_id')
    def _onchange_date(self):
        if self.patient_id and self.patient_id.date:
            self.admission_date = self.patient_id.date

    @api.depends('line_ids.price_subtotal')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(line.price_subtotal for line in rec.line_ids)

    @api.depends('admission_date', 'discharge_date')
    def _compute_num_of_days(self):
        for rec in self:
            if rec.admission_date and rec.discharge_date:
                x = rec.discharge_date - rec.admission_date
                rec.number_of_days = x.days
            else:
                rec.number_of_days = 0

    @api.depends('number_of_days', 'room_price_per_day')
    def _compute_room_total_amount(self):
        for rec in self:
            rec.room_total_amount = rec.number_of_days * rec.room_price_per_day