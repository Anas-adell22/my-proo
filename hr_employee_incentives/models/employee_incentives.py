# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# حالات الدفعة التي تُحسب كمدفوعة
PAID_PAYMENT_STATES = ('in_process', 'paid', 'posted')
# أيام الشهر لتحويل "أيام" المكافأة إلى مبلغ عند الصرف بدفعة
DAYS_IN_MONTH = 30

class EmployeePenalty(models.Model):
    _name = 'employee.penalty'
    _description = 'جزاء موظف'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name')
    employee_id = fields.Many2one('hr.employee', string='الموظف', required=True)
    user_id = fields.Many2one('res.users', string='المسؤول', default=lambda self: self.env.user)
    penalty_type_id = fields.Many2one('penalty.type', string='نوع المخالفة', required=True, tracking=True)
    amount = fields.Monetary(string='المبلغ', currency_field='currency_id',
                             compute='_compute_from_type', store=True, readonly=False)
    days = fields.Float(string='الأيام', compute='_compute_from_type', store=True, readonly=False)
    currency_id = fields.Many2one('res.currency',string='العملة',default=lambda self: self.env.company.currency_id)
    date = fields.Date('Date', default=fields.Date.today(), required=True)
    note = fields.Html('Note')
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('approved', 'معتمد'),
        ('rejected', 'مرفوض'),
        ('cancelled', 'ملغى'),
        ('discounted', 'تم الخصم')
    ], string='الحالة', default='draft', tracking=True)
    
    month = fields.Selection([
        ('1','يناير'), ('2','فبراير'), ('3','مارس'), ('4','أبريل'),
        ('5','مايو'), ('6','يونيو'), ('7','يوليو'), ('8','أغسطس'),
        ('9','سبتمبر'), ('10','أكتوبر'), ('11','نوفمبر'), ('12','ديسمبر'),
    ], string='الشهر', compute="_compute_month", store=True, readonly=True)
    year = fields.Integer(string='السنة', compute="_compute_year", store=True)
    apply_type = fields.Selection([
        ('amount', 'مبلغ'),
        ('days', 'أيام'),
    ], string='نوع الخصم', compute='_compute_from_type', store=True, readonly=False, default='amount')

    # حقول الـ smart buttons
    penalty_count = fields.Integer(string='المخالفات',compute='_compute_penalty_count')
    payslip_count = fields.Integer(string='مقبوضات راتب',compute='_compute_payslip_count')

    @api.depends('penalty_type_id')
    def _compute_from_type(self):
        """القيم الافتراضية من نوع المخالفة، وتفضل قابلة للتعديل يدويًا في المسودة."""
        for rec in self:
            t = rec.penalty_type_id
            rec.apply_type = t.apply_type or rec.apply_type or 'amount'
            if rec.apply_type == 'days':
                rec.days = t.days or rec.days or 0.0
                rec.amount = rec.amount or 0.0
            else:
                rec.amount = t.value or rec.amount or 0.0
                rec.days = rec.days or 0.0

    def _get_value(self):
        """القيمة المدخلة: أيام أو مبلغ حسب نوع الخصم."""
        self.ensure_one()
        return self.days if self.apply_type == 'days' else self.amount

    @api.depends('employee_id', 'state')
    def _compute_payslip_count(self):
        receipts = self.env['payroll.receipt'].sudo()
        for rec in self:
            rec.payslip_count = receipts.search_count([
                ('source_model', '=', rec._name),
                ('source_id', '=', rec.id),
            ]) if rec.id else 0

    def action_open_payslips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('مقبوضات راتب'),
            'res_model': 'payroll.receipt',
            'view_mode': 'list,form',
            'domain': [('source_model', '=', self._name), ('source_id', '=', self.id)],
        }


    @api.depends('employee_id', 'penalty_type_id')
    def _compute_penalty_count(self):
        for rec in self:
            rec.penalty_count = self.env['employee.penalty'].search_count([
                ('employee_id', '=', rec.employee_id.id),
                ('penalty_type_id', '=', rec.penalty_type_id.id),
            ])

    def action_open_employee_penalties(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('الجزاءات'),
            'res_model': 'employee.penalty',
            'view_mode': 'list,form',
            'domain': [
                ('employee_id', '=', self.employee_id.id),
                ('penalty_type_id', '=', self.penalty_type_id.id),
            ],
        }

    @api.depends('employee_id', 'penalty_type_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.employee_id.name} - {record.penalty_type_id.name}'

    @api.constrains('date')
    def check_date(self):
        if self.date > fields.Date.today():
            raise ValidationError(_("لا يمكن تسجيل جزاء بتاريخ مستقبلي"))

    @api.depends('date')
    def _compute_month(self):
        for record in self:
            if record.date:
                record.month = str(record.date.month)

    @api.depends('date')
    def _compute_year(self):
        for record in self:
            if record.date:
                record.year = record.date.year

    def _register_receipt(self):
        """عند الاعتماد: تسجيل الجزاء فورًا في مقبوضات الراتب (بدون الاعتماد على العقد أو كشف المرتب)."""
        self.ensure_one()
        self.env['payroll.receipt'].register(self, 'penalty', 'deduction', self.penalty_type_id.name)

    def action_approve(self):
        for record in self:
            if record.state not in ('draft', 'discounted', 'approved'):
                raise UserError(_('يمكنك اعتماد السجلات في حالة المسودة فقط.'))
            if record._get_value() <= 0:
                raise UserError(_('يجب إدخال قيمة الخصم (مبلغ أو أيام) أكبر من صفر قبل الاعتماد.'))
            record.write({'state': 'approved'})
            record._register_receipt()

    def action_reject(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('يمكنك رفض السجلات في حالة المسودة فقط.'))
            record.write({'state': 'rejected'})

    def action_cancel(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(_('يمكنك إلغاء السجلات المعتمدة فقط.'))
            receipt = self.env['payroll.receipt'].sudo().search([
                ('source_model', '=', record._name),
                ('source_id', '=', record.id),
                ('state', '=', 'included'),
            ], limit=1)
            payslip = receipt.payslip_id
            if payslip and payslip.state != 'draft':
                raise UserError(_('يوجد خصم لهذا الجزاء في كشوف الرواتب.'))
            self.env['payroll.receipt'].cancel_for(record)
            record.write({'state': 'cancelled'})
            if payslip:
                payslip._sync_incentive_inputs()

    def action_discount(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(_('يمكنك خصم السجلات المعتمدة فقط.'))
            record.write({'state': 'discounted'})

class EmployeeReward(models.Model):
    _name = 'employee.reward'
    _description = 'مكافأة موظف'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name')
    employee_id = fields.Many2one('hr.employee', string='الموظف', required=True)
    user_id = fields.Many2one('res.users', string='المسؤول', default=lambda self: self.env.user)
    reward_type_id = fields.Many2one('reward.type', string='نوع المكافأة', required=True, tracking=True)
    reward_category = fields.Selection(related='reward_type_id.reward_category', string='التصنيف',
                                       store=True, readonly=True)
    amount = fields.Monetary(string='المبلغ', currency_field='currency_id',
                             compute='_compute_from_type', store=True, readonly=False)
    days = fields.Float(string='الأيام', compute='_compute_from_type', store=True, readonly=False)
    disbursement_type = fields.Selection([
        ('payment', 'صرف فوري (دفعة)'),
        ('payroll', 'مقبوضات الراتب'),
    ], string='طريقة الصرف', compute='_compute_disbursement_type', store=True,
        readonly=False, tracking=True)
    currency_id = fields.Many2one('res.currency',string='العملة',default=lambda self: self.env.company.currency_id)
    date = fields.Date('Date', default=fields.Date.today(), required=True)
    note = fields.Html('Note')
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('approved', 'معتمد'),
        ('rejected', 'مرفوض'),
        ('cancelled', 'ملغى'),
        ('paid', 'تم الصرف')
    ], string='الحالة', default='draft', tracking=True)
    
    month = fields.Selection([
        ('1','يناير'), ('2','فبراير'), ('3','مارس'), ('4','أبريل'),
        ('5','مايو'), ('6','يونيو'), ('7','يوليو'), ('8','أغسطس'),
        ('9','سبتمبر'), ('10','أكتوبر'), ('11','نوفمبر'), ('12','ديسمبر'),
    ], string='الشهر', compute="_compute_month", store=True, readonly=True)
    year = fields.Integer(string='السنة', compute="_compute_year", store=True)
    apply_type = fields.Selection([
        ('amount', 'مبلغ'),
        ('days', 'أيام'),
    ], string='نوع المكافأة', compute='_compute_from_type', store=True, readonly=False, default='amount')

    reward_count = fields.Integer(string='المكافأت',compute='_compute_reward_count')
    payslip_count = fields.Integer(string='مقبوضات راتب',compute='_compute_payslip_count')
    payment_ids = fields.One2many('account.payment', 'reward_id', string='الدفعات', readonly=True)
    payment_count = fields.Integer(string='عدد الدفعات', compute='_compute_payment_count')
    paid_amount = fields.Monetary(string='المدفوع', currency_field='currency_id',
                                  compute='_compute_paid_amount', store=True)

    @api.depends('reward_type_id')
    def _compute_from_type(self):
        """القيم الافتراضية من نوع المكافأة، وتفضل قابلة للتعديل يدويًا في المسودة."""
        for rec in self:
            t = rec.reward_type_id
            rec.apply_type = t.apply_type or rec.apply_type or 'amount'
            if rec.apply_type == 'days':
                rec.days = t.days or rec.days or 0.0
                rec.amount = rec.amount or 0.0
            else:
                rec.amount = t.value or rec.amount or 0.0
                rec.days = rec.days or 0.0

    def _get_value(self):
        """القيمة المدخلة: أيام أو مبلغ حسب نوع المكافأة."""
        self.ensure_one()
        return self.days if self.apply_type == 'days' else self.amount

    @api.depends('reward_type_id')
    def _compute_disbursement_type(self):
        for rec in self:
            rec.disbursement_type = rec.reward_type_id.disbursement_type or 'payroll'

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.payment_ids)

    @api.depends('payment_ids.state', 'payment_ids.amount')
    def _compute_paid_amount(self):
        for rec in self:
            rec.paid_amount = sum(p.amount for p in rec.payment_ids if p.state in PAID_PAYMENT_STATES)

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('الدفعات'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('reward_id', '=', self.id)],
        }

    @api.depends('employee_id', 'state')
    def _compute_payslip_count(self):
        receipts = self.env['payroll.receipt'].sudo()
        for rec in self:
            rec.payslip_count = receipts.search_count([
                ('source_model', '=', rec._name),
                ('source_id', '=', rec.id),
            ]) if rec.id else 0

    def action_open_payslips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('مقبوضات راتب'),
            'res_model': 'payroll.receipt',
            'view_mode': 'list,form',
            'domain': [('source_model', '=', self._name), ('source_id', '=', self.id)],
        }

    @api.depends('employee_id', 'reward_type_id')
    def _compute_reward_count(self):
        for rec in self:
            rec.reward_count = self.env['employee.reward'].search_count([
                ('employee_id', '=', rec.employee_id.id),
                ('reward_type_id', '=', rec.reward_type_id.id),
            ])

    def action_open_employee_rewards(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('المكافآت'),
            'res_model': 'employee.reward',
            'view_mode': 'list,form',
            'domain': [
                ('employee_id', '=', self.employee_id.id),
                ('reward_type_id', '=', self.reward_type_id.id),
            ],
        }

    @api.depends('employee_id', 'reward_type_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.employee_id.name} - {record.reward_type_id.name}'

    @api.constrains('date')
    def check_date(self):
        if self.date > fields.Date.today():
            raise ValidationError(_("لا يمكن تسجيل مكافأة بتاريخ مستقبلي"))

    @api.depends('date')
    def _compute_month(self):
        for record in self:
            if record.date:
                record.month = str(record.date.month)

    @api.depends('date')
    def _compute_year(self):
        for record in self:
            if record.date:
                record.year = record.date.year

    def _register_receipt(self):
        """عند الاعتماد (طريقة الصرف: مقبوضات الراتب): تسجيل المكافأة فورًا في مقبوضات الراتب."""
        self.ensure_one()
        self.env['payroll.receipt'].register(self, 'reward', 'addition', self.reward_type_id.name)

    def _get_payment_amount(self):
        """قيمة الدفعة: المبلغ، أو الأيام محوّلة لمبلغ حسب أجر العقد."""
        self.ensure_one()
        if self.apply_type == 'days':
            contract = self.employee_id.contract_id if 'contract_id' in self.employee_id._fields else False
            wage = contract.wage if contract else 0.0
            return (self.days or 0.0) * wage / DAYS_IN_MONTH
        return self.amount or 0.0

    def _create_payment(self):
        """عند الاعتماد (طريقة الصرف: صرف فوري): إنشاء دفعة للموظف في نموذج الدفعات."""
        self.ensure_one()
        if self.payment_ids.filtered(lambda p: p.state not in ('canceled', 'cancel', 'rejected')):
            return self.payment_ids
        partner = self.employee_id.work_contact_id
        if not partner:
            raise UserError(_('الموظف %s ليس له جهة اتصال (work contact) لإنشاء الدفعة.') % self.employee_id.display_name)
        amount = self._get_payment_amount()
        if amount <= 0:
            raise UserError(_('يجب أن تكون قيمة المكافأة أكبر من صفر للصرف بدفعة.'))
        payment_model = self.env['account.payment']
        vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': partner.id,
            'amount': amount,
            'currency_id': self.currency_id.id,
            'date': fields.Date.context_today(self),
            'reward_id': self.id,
        }
        if 'memo' in payment_model._fields:
            vals['memo'] = self.display_name
        elif 'ref' in payment_model._fields:
            vals['ref'] = self.display_name
        return payment_model.create(vals)

    def _sync_payment_state(self):
        """يحدّث حالة المكافأة (معتمد / تم الصرف) حسب حالة دفعاتها."""
        for rec in self:
            if rec.disbursement_type != 'payment' or rec.state not in ('approved', 'paid'):
                continue
            paid = sum(p.amount for p in rec.payment_ids if p.state in PAID_PAYMENT_STATES)
            target = rec._get_payment_amount()
            new_state = 'paid' if target and paid >= target else 'approved'
            if new_state != rec.state:
                rec.sudo().write({'state': new_state})

    def action_approve(self):
        for record in self:
            if record.state not in ('draft', 'paid', 'approved'):
                raise UserError(_('يمكنك اعتماد السجلات في حالة المسودة فقط.'))
            if record.state == 'draft' and record._get_value() <= 0:
                raise UserError(_('يجب إدخال قيمة المكافأة (مبلغ أو أيام) أكبر من صفر قبل الاعتماد.'))
            if record.disbursement_type == 'payment':
                if record.state == 'draft':
                    record.write({'state': 'approved'})
                record._create_payment()
                continue
            record.write({'state': 'approved'})
            record._register_receipt()

    def action_reject(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('يمكنك رفض السجلات في حالة المسودة فقط.'))
            record.write({'state': 'rejected'})

    def action_cancel(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(_('يمكنك إلغاء السجلات المعتمدة فقط.'))
            if record.disbursement_type == 'payment':
                if record.payment_ids.filtered(lambda p: p.state not in ('draft', 'canceled', 'cancel', 'rejected')):
                    raise UserError(_('توجد دفعات مؤكدة لهذه المكافأة، ألغِها من الدفعات أولاً.'))
                record.payment_ids.filtered(lambda p: p.state == 'draft').unlink()
                record.write({'state': 'cancelled'})
                continue
            receipt = self.env['payroll.receipt'].sudo().search([
                ('source_model', '=', record._name),
                ('source_id', '=', record.id),
                ('state', '=', 'included'),
            ], limit=1)
            payslip = receipt.payslip_id
            if payslip and payslip.state != 'draft':
                raise UserError(_('توجد مكافأة لهذا السجل في كشوف الرواتب.'))
            self.env['payroll.receipt'].cancel_for(record)
            record.write({'state': 'cancelled'})
            if payslip:
                payslip._sync_incentive_inputs()

    def action_paid(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(_('يمكنك تحديد السجلات المعتمدة كمدفوعة فقط.'))
            record.write({'state': 'paid'})

