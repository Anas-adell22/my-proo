# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class PenaltyType(models.Model):
    _name = 'penalty.type'
    _description = 'نوع الجزاء'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('الاسم', required=True)
    apply_type = fields.Selection([
        ('amount', 'مبلغ'),
        ('days', 'أيام'),
    ], string='نوع الخصم', required=True, default='amount', tracking=True)
    currency_id = fields.Many2one('res.currency', string='العملة',
                                  default=lambda self: self.env.company.currency_id)
    value = fields.Monetary(string='المبلغ', currency_field='currency_id', tracking=True)
    days = fields.Float(string='الأيام', tracking=True)
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('approved', 'معتمد'),
        ('cancel', 'ملغى'),
    ], default='draft', string='الحالة', tracking=True)

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_cancel(self):
        self.write({'state': 'cancel'})


class RewardType(models.Model):
    _name = 'reward.type'
    _description = 'نوع المكافأة'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('الاسم', required=True)
    reward_category = fields.Selection([
        ('reward', 'مكافأة'),
        ('grant', 'منحة'),
        ('incentive', 'حافز'),
    ], string='التصنيف', required=True, default='reward', tracking=True)
    apply_type = fields.Selection([
        ('amount', 'مبلغ'),
        ('days', 'أيام'),
    ], string='نوع المكافأة', required=True, default='amount', tracking=True)
    currency_id = fields.Many2one('res.currency', string='العملة',
                                  default=lambda self: self.env.company.currency_id)
    value = fields.Monetary(string='المبلغ', currency_field='currency_id', tracking=True)
    days = fields.Float(string='الأيام', tracking=True)
    disbursement_type = fields.Selection([
        ('payment', 'صرف فوري (دفعة)'),
        ('payroll', 'مقبوضات الراتب'),
    ], string='طريقة الصرف', required=True, default='payroll', tracking=True)
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('approved', 'معتمد'),
        ('cancel', 'ملغى'),
    ], default='draft', string='الحالة', tracking=True)

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_cancel(self):
        self.write({'state': 'cancel'})
