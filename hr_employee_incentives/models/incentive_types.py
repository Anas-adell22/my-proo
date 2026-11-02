# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class PenaltyType(models.Model):
    _name = 'penalty.type'
    _description = 'نوع الجزاء'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('الاسم', required=True)
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
    # قديم: التصنيف بقى بيتحدد في المكافأة نفسها (employee.reward).
    # سيبنا الحقل هنا من غير required ومن غير ما يظهر في أي شاشة، عشان عمود
    # قاعدة البيانات القديم (NOT NULL) ما يعملش مشكلة لما نضيف نوع جديد.
    reward_category = fields.Selection([
        ('reward', 'مكافأة'),
        ('grant', 'منحة'),
        ('incentive', 'حافز'),
    ], string='التصنيف (قديم)')
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('approved', 'معتمد'),
        ('cancel', 'ملغى'),
    ], default='draft', string='الحالة', tracking=True)

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_cancel(self):
        self.write({'state': 'cancel'})
