# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PayrollReceipt(models.Model):
    _name = 'payroll.receipt'
    _description = 'مقبوضات الراتب'
    _order = 'date desc, id desc'

    name = fields.Char(string='البيان', required=True)
    employee_id = fields.Many2one('hr.employee', string='الموظف', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='الشركة', default=lambda self: self.env.company)
    date = fields.Date(string='التاريخ', required=True, index=True)
    receipt_type = fields.Selection([
        ('penalty', 'جزاء'),
        ('reward', 'مكافأة'),
        ('grievance', 'تظلم'),
        ('petition', 'التماس'),
    ], string='النوع', required=True)
    effect = fields.Selection([
        ('deduction', 'خصم'),
        ('addition', 'إضافة'),
    ], string='الأثر على الراتب', required=True)
    apply_type = fields.Selection([
        ('amount', 'مبلغ'),
        ('days', 'أيام'),
    ], string='طريقة التطبيق', default='amount')
    currency_id = fields.Many2one('res.currency', string='العملة',
                                  default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary(string='القيمة', currency_field='currency_id')
    net_amount = fields.Monetary(string='الصافي', currency_field='currency_id',
                                 compute='_compute_net_amount', store=True)
    state = fields.Selection([
        ('pending', 'معلّق'),
        ('included', 'داخل كشف المرتب'),
        ('cancelled', 'ملغى'),
    ], string='الحالة', default='pending', required=True)
    payslip_id = fields.Many2one('hr.payslip', string='كشف المرتب', ondelete='set null')
    source_model = fields.Char(string='المصدر (موديل)', index=True)
    source_id = fields.Integer(string='المصدر (رقم)', index=True)

    @api.depends('amount', 'effect', 'apply_type')
    def _compute_net_amount(self):
        for rec in self:
            if rec.apply_type == 'days':
                rec.net_amount = 0.0
            else:
                rec.net_amount = rec.amount if rec.effect == 'addition' else -rec.amount

    # ------------------------------------------------------------------
    # واجهة للتسجيل من السجلات المصدر (جزاء / مكافأة / ...)
    # ------------------------------------------------------------------
    @api.model
    def register(self, source, receipt_type, effect, name):
        """ينشئ (أو يحدّث) سجل مقبوضات الراتب الخاص بالسجل المصدر."""
        receipts = self.sudo()
        existing = receipts.search([
            ('source_model', '=', source._name),
            ('source_id', '=', source.id),
        ], limit=1)
        vals = {
            'name': name or source.display_name,
            'employee_id': source.employee_id.id,
            'date': source.date,
            'receipt_type': receipt_type,
            'effect': effect,
            'apply_type': source.apply_type or 'amount',
            'amount': source._get_value(),
            'currency_id': (source.currency_id or self.env.company.currency_id).id,
            'company_id': source.employee_id.company_id.id or self.env.company.id,
        }
        if existing:
            if existing.state == 'included':
                return existing
            existing.write(dict(vals, state='pending'))
            return existing
        return receipts.create(dict(vals, source_model=source._name, source_id=source.id, state='pending'))

    @api.model
    def cancel_for(self, source):
        """يلغي سجل المقبوضات الخاص بالسجل المصدر."""
        self.sudo().search([
            ('source_model', '=', source._name),
            ('source_id', '=', source.id),
            ('state', '!=', 'cancelled'),
        ]).write({'state': 'cancelled', 'payslip_id': False})

    def action_open_source(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.source_model,
            'res_id': self.source_id,
            'view_mode': 'form',
            'target': 'current',
        }
