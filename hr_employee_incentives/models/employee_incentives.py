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
    amount = fields.Monetary(string='المبلغ', currency_field='currency_id')
    days = fields.Float(string='الأيام')
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
    ], string='نوع الخصم', default='amount')

    # حقول الـ smart buttons
    penalty_count = fields.Integer(string='المخالفات',compute='_compute_penalty_count')
    payslip_count = fields.Integer(string='مقبوضات راتب',compute='_compute_payslip_count')

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
            if record.state == 'draft' and record._get_value() <= 0:
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
            payslip_input = record.env['hr.payslip.input'].search([('penalty_id', '=', record.id)], limit=1)
            if payslip_input:
                if payslip_input.payslip_id.state == 'draft':
                    payslip_input.unlink()
                else:
                    raise UserError(_('يوجد خصم لهذا الجزاء في كشوف الرواتب.'))
            self.env['payroll.receipt'].cancel_for(record)
            record.write({'state': 'cancelled'})

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
    # التصنيف بيتحدد هنا وقت تسجيل المكافأة للموظف (مش من نوع المكافأة)
    reward_category = fields.Selection([
        ('reward', 'مكافأة'),
        ('grant', 'منحة'),
        ('incentive', 'حافز'),
    ], string='التصنيف', required=True, default='reward', tracking=True)
    amount = fields.Monetary(string='المبلغ', currency_field='currency_id')
    days = fields.Float(string='الأيام')
    # بتتحدد تلقائي من التصنيف: مكافأة = مقبوضات الراتب، منحة / حافز = دفعة فورية
    disbursement_type = fields.Selection([
        ('payment', 'صرف فوري (دفعة)'),
        ('payroll', 'مقبوضات الراتب'),
    ], string='طريقة الصرف', compute='_compute_disbursement_type',
        store=True, tracking=True)
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
    ], string='نوع المكافأة', default='amount')

    reward_count = fields.Integer(string='المكافأت',compute='_compute_reward_count')
    payslip_count = fields.Integer(string='مقبوضات راتب',compute='_compute_payslip_count')
    payment_ids = fields.One2many('account.payment', 'reward_id', string='الدفعات', readonly=True)
    payment_count = fields.Integer(string='عدد الدفعات', compute='_compute_payment_count')
    paid_amount = fields.Monetary(string='المدفوع', currency_field='currency_id',
                                  compute='_compute_paid_amount', store=True)
    # المتبقي بعد الدفعات المؤكدة، وبيتصرف من مقبوضات الراتب
    remaining_amount = fields.Monetary(string='المتبقي (مقبوضات الراتب)',
                                       currency_field='currency_id',
                                       compute='_compute_remaining_amount', store=True)

    def _get_value(self):
        """القيمة المدخلة: أيام أو مبلغ حسب نوع المكافأة."""
        self.ensure_one()
        return self.days if self.apply_type == 'days' else self.amount

    @api.depends('reward_category')
    def _compute_disbursement_type(self):
        for rec in self:
            # السجلات المعتمدة بتفضل على طريقة صرفها زي ما هي
            if rec.state != 'draft' and rec.disbursement_type:
                continue
            if rec.reward_category == 'reward':
                rec.disbursement_type = 'payroll'
            else:
                rec.disbursement_type = 'payment'

    @api.model
    def _update_draft_disbursement(self):
        """بتتنفذ مع الـ Upgrade: تحديث طريقة الصرف للمسودات القديمة حسب التصنيف."""
        self.search([('state', '=', 'draft')])._compute_disbursement_type()

    @api.model
    def _resync_payment_rewards(self):
        """بتتنفذ مع الـ Upgrade: تسجيل متبقي المكافآت اللي اتصرف جزء منها بدفعة في مقبوضات الراتب."""
        self.search([
            ('disbursement_type', '=', 'payment'),
            ('state', 'in', ('approved', 'paid')),
        ])._sync_payment_state()

    @api.depends('disbursement_type', 'paid_amount', 'amount', 'days', 'apply_type')
    def _compute_remaining_amount(self):
        for rec in self:
            if rec.disbursement_type == 'payment' and rec.paid_amount > 0:
                remaining = rec._get_payment_amount() - rec.paid_amount
                rec.remaining_amount = max(rec.currency_id.round(remaining), 0.0)
            else:
                rec.remaining_amount = 0.0

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

    def _sync_remainder_receipt(self, paid, target):
        """لو الدفعات المؤكدة أقل من قيمة المكافأة، المتبقي بيتسجل في مقبوضات الراتب."""
        self.ensure_one()
        remainder = self.currency_id.round(target - paid)
        receipts = self.env['payroll.receipt'].sudo()
        if paid > 0 and remainder > 0:
            receipts.register(
                self, 'reward', 'addition',
                '%s (المتبقي)' % self.reward_type_id.name,
                amount=remainder, apply_type='amount')
        else:
            # مفيش متبقي: نلغي المقبوض المعلّق (اللي دخل كشف مرتب مبنلمسوش)
            pending = receipts.search([
                ('source_model', '=', self._name),
                ('source_id', '=', self.id),
                ('state', '=', 'pending'),
            ])
            pending.write({'state': 'cancelled'})

    def _sync_payment_state(self):
        """يحدّث حالة المكافأة (معتمد / تم الصرف) حسب دفعاتها،
        وأي متبقي بعد الدفعات المؤكدة بيتسجل في مقبوضات الراتب."""
        receipts = self.env['payroll.receipt'].sudo()
        for rec in self:
            if rec.disbursement_type != 'payment' or rec.state not in ('approved', 'paid'):
                continue
            paid = sum(p.amount for p in rec.payment_ids if p.state in PAID_PAYMENT_STATES)
            target = rec._get_payment_amount()
            rec._sync_remainder_receipt(paid, target)
            # المتبقي اتصرف فعلاً لو كشف المرتب اللي هو فيه اتدفع
            remainder_paid = receipts.search_count([
                ('source_model', '=', rec._name),
                ('source_id', '=', rec.id),
                ('state', '=', 'included'),
                ('payslip_id.state', '=', 'paid'),
            ])
            if (target and paid >= target) or remainder_paid:
                new_state = 'paid'
            else:
                new_state = 'approved'
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
                record._sync_payment_state()
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
            payslip_input = record.env['hr.payslip.input'].search([('reward_id', '=', record.id)], limit=1)
            if payslip_input:
                if payslip_input.payslip_id.state == 'draft':
                    payslip_input.unlink()
                else:
                    raise UserError(_('توجد مكافأة لهذا السجل في كشوف الرواتب.'))
            self.env['payroll.receipt'].cancel_for(record)
            record.write({'state': 'cancelled'})

    def action_paid(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(_('يمكنك تحديد السجلات المعتمدة كمدفوعة فقط.'))
            record.write({'state': 'paid'})
