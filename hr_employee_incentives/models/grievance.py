from odoo import api, fields, models
from odoo.exceptions import UserError

# حالات الدفعة التي تُحسب كمدفوعة (قيد التنفيذ أو مدفوع)
PAID_PAYMENT_STATES = ('in_process', 'paid', 'posted')


class Grievance(models.Model):
    _name = 'hr.grievance'
    _description = 'تظلمات'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence asc, id asc'

    # --- أساسي ---
    name = fields.Char(string='الكود', readonly=True, copy=False, default='New', tracking=True)
    active = fields.Boolean(string='نشط', default=True)
    sequence = fields.Integer(string='التسلسل', default=10)
    value = fields.Float(string='القيمة', tracking=True)
    signature = fields.Binary(string='التوقيع', attachment=True)

    # --- العلاقات ---
    employee_id = fields.Many2one(
        'hr.employee', string='الموظف', required=True, tracking=True,
        default=lambda self: self.env.user.employee_id)
    company_id = fields.Many2one('res.company', string='الشركة', required=True,
                                 default=lambda self: self.env.company)
    partner_id = fields.Many2one(
        'res.partner', string='جهة الاتصال',
        compute='_compute_partner_id', store=True, readonly=False, tracking=True)
    complained_department_id = fields.Many2one('hr.department', string='القسم المشكو منه')
    executor_ids = fields.Many2many('hr.employee', 'hr_grievance_executor_rel', 'grievance_id', 'employee_id',
                                    string='منفذ القرار')
    line_ids = fields.One2many('hr.grievance.line', 'grievance_id', string='أسطر جديدة')
    payment_ids = fields.One2many('account.payment', 'grievance_id', string='الدفعات', readonly=True)

    # --- حقول مرتبطة بالموظف ---
    job_title = fields.Char(string='المسمى الوظيفي', related='employee_id.job_title', store=True, readonly=True)
    employee_code = fields.Char(string='كود الموظف', related='employee_id.barcode', readonly=True)
    manager_id = fields.Many2one('hr.employee', string='المدير المباشر', related='employee_id.parent_id',
                                 store=True, readonly=True)
    department_id = fields.Many2one('hr.department', string='القسم', related='employee_id.department_id',
                                    store=True, readonly=True)

    # --- نصوص ---
    description = fields.Text(string='وصف التظلم')
    department_reply = fields.Text(string='رد القسم المشكو منه')
    reply = fields.Text(string='رد على طلب التظلم')
    notes = fields.Text(string='ملاحظة')

    # --- الحالات ---
    state = fields.Selection([
        ('request', 'طلب'),
        ('in_progress', 'قيد التنفيذ'),
        ('rejected', 'مرفوض'),
        ('done', 'منتهي'),
    ], string='حالة', compute='_compute_state', store=True, readonly=False, tracking=True)
    decision = fields.Selection([
        ('accepted', 'قبول'),
        ('rejected', 'رفض'),
    ], string='القرار', tracking=True, copy=False)
    financial_state = fields.Selection([
        ('none', 'لا يوجد أثر مالي'),
        ('pending', 'قيد الصرف'),
        ('done', 'تم التنفيذ'),
    ], string='حالة مالية', default='none')
    hold_state = fields.Selection([
        ('active', 'ساري'),
        ('suspended', 'موقوف'),
    ], string='الحالة وقف', default='active')

    # --- المبالغ ---
    paid_amount = fields.Float(string='المدفوع', compute='_compute_paid_amount', store=True)
    remaining_amount = fields.Float(string='المتبقي', compute='_compute_remaining_amount', store=True)

    # --- العدادات ---
    grievance_count = fields.Integer(string='عدد التظلمات', compute='_compute_grievance_count')
    total_grievance_count = fields.Integer(string='إجمالي التظلمات', compute='_compute_grievance_count')
    payment_count = fields.Integer(string='عدد الدفعات', compute='_compute_payment_count')

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('employee_id')
    def _compute_partner_id(self):
        for rec in self:
            rec.partner_id = rec.employee_id.work_contact_id

    @api.depends('payment_ids.state', 'payment_ids.amount')
    def _compute_paid_amount(self):
        for rec in self:
            rec.paid_amount = sum(
                p.amount for p in rec.payment_ids if p.state in PAID_PAYMENT_STATES)

    @api.depends('value', 'paid_amount')
    def _compute_remaining_amount(self):
        for rec in self:
            rec.remaining_amount = rec.value - rec.paid_amount

    @api.depends('decision', 'remaining_amount', 'value')
    def _compute_state(self):
        for rec in self:
            if rec.decision == 'accepted' and rec.state in ('in_progress', 'done'):
                rec.state = 'done' if rec.value and rec.remaining_amount <= 0 else 'in_progress'
            elif not rec.state:
                rec.state = 'request'

    @api.depends('employee_id')
    def _compute_grievance_count(self):
        for rec in self:
            if rec.employee_id:
                domain = [('employee_id', '=', rec.employee_id.id)]
                rec.total_grievance_count = self.search_count(domain)
                rec.grievance_count = self.search_count(domain + [('decision', '=', 'rejected')])
            else:
                rec.total_grievance_count = 0
                rec.grievance_count = 0

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.payment_ids)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.grievance') or 'New'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # الأزرار
    # ------------------------------------------------------------------
    def action_in_progress(self):
        self.write({'state': 'in_progress'})

    def action_accept(self):
        """قبول: يبقى في نفس الحالة وينشئ دفعة للموظف."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError('يجب تحديد جهة الاتصال للموظف قبل القبول.')
        if self.value <= 0:
            raise UserError('يجب إدخال قيمة أكبر من صفر قبل القبول.')
        payment_model = self.env['account.payment']
        vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_id.id,
            'amount': self.value,
            'date': fields.Date.context_today(self),
            'grievance_id': self.id,
        }
        if 'memo' in payment_model._fields:
            vals['memo'] = self.name
        elif 'ref' in payment_model._fields:
            vals['ref'] = self.name
        payment = payment_model.create(vals)
        self.decision = 'accepted'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reject(self):
        self.write({'decision': 'rejected', 'state': 'rejected'})

    def action_reset(self):
        self.write({'decision': False, 'state': 'request'})

    # ------------------------------------------------------------------
    # أزرار الإحصاء
    # ------------------------------------------------------------------
    def action_view_total(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'إجمالي التظلمات',
            'res_model': 'hr.grievance',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.employee_id.id)],
        }

    def action_view_rejected(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'التظلمات المرفوضة',
            'res_model': 'hr.grievance',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.employee_id.id), ('decision', '=', 'rejected')],
        }

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'الدفعات',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('grievance_id', '=', self.id)],
        }
