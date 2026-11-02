import base64

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
          'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']

QUARTERS = ['الربع الأول', 'الربع الثاني', 'الربع الثالث', 'الربع الرابع']


class ReconciliationPeriodOption(models.Model):
    _name = 'reconciliation.period.option'
    _description = 'Period Option'
    _order = 'sort_key'

    name = fields.Char(required=True)
    period_type = fields.Selection([
        ('monthly', 'شهري'),
        ('quarterly', 'ربع سنوي'),
        ('yearly', 'سنوي'),
    ], required=True)
    sort_key = fields.Integer()

    @api.model
    def _create_if_missing(self, period_type, year, number, name):
        key = year * 100 + number
        found = self.search([
            ('period_type', '=', period_type),
            ('sort_key', '=', key),
        ], limit=1)
        if not found:
            self.create({
                'name': name,
                'period_type': period_type,
                'sort_key': key,
            })

    @api.model
    def generate_options(self):
        start = fields.Date.today().year
        for year in range(start, start + 10):
            for month in range(1, 13):
                self._create_if_missing(
                    'monthly', year, month,
                    '%s %s' % (MONTHS[month - 1], year))
            for quarter in range(1, 5):
                self._create_if_missing(
                    'quarterly', year, quarter,
                    '%s %s' % (QUARTERS[quarter - 1], year))
            self._create_if_missing('yearly', year, 1, str(year))


class ReconciliationBalanceType(models.Model):
    _name = 'reconciliation.balance.type'
    _description = 'Customer Balance Type'

    name = fields.Char(required=True)
    code = fields.Selection([
        ('negative', 'سالب'),
        ('positive', 'موجب'),
        ('zero', 'صفر'),
    ], required=True)


class ReconciliationPeriod(models.Model):
    _name = 'reconciliation.period'
    _description = 'Reconciliation Period'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(compute='_compute_name', store=True)

    years_count = fields.Integer(
        string='عدد السنين', required=True, default=3)

    period_type = fields.Selection([
        ('monthly', 'شهري'),
        ('quarterly', 'ربع سنوي'),
        ('yearly', 'سنوي'),
    ], string='نوع الفترة', required=True, default='monthly')

    option_id = fields.Many2one(
        'reconciliation.period.option', string='المطابقة', required=True)

    # (1) تاريخ المطابقة: أي تعديل فيه بيتنسخ على كل بنود "مطلوب مطابقة"
    date = fields.Date(
        string='التاريخ', default=fields.Date.today, tracking=True)

    # (3) حالة المطابقة
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('in_progress', 'قيد التنفيذ'),
        ('done', 'منتهي'),
        ('cancelled', 'ملغي'),
    ], string='الحالة', default='draft', required=True,
        copy=False, tracking=True)

    # المندوب: لو اتحدد، جلب العملاء بيجيب عملاءه بس. لو فاضي بيجيب الكل
    # (2) المناديب التابعين للشركة المحددة (حقل الشركة في جهة الاتصال)
    user_id = fields.Many2one(
        'res.users', string='المندوب',
        domain="[('partner_id.company_id', '=', company_id)]")

    balance_type_ids = fields.Many2many(
        'reconciliation.balance.type', string='نوع العملاء')

    line_ids = fields.One2many(
        'reconciliation.period.line', 'period_id', string='العملاء')

    customer_count = fields.Integer(string = 'عدد العملاء', compute= '_compute_customer_count',store = True)

    request_ids = fields.One2many(
        'reconciliation.request', 'period_id', string='مطلوب مطابقة')

    # تحديد كل العملاء اللي لسه متضافوش
    select_all = fields.Boolean(string='تحديد الكل')

    # (7) تحديد كل بنود مطلوب المطابقة للطباعة
    select_all_print = fields.Boolean(string='تحديد الكل للطباعة')

    min_key = fields.Integer(compute='_compute_range')
    max_key = fields.Integer(compute='_compute_range')

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='الشركة',
        required=True,
        default=lambda self: self.env.company
    )

    @api.depends('period_type', 'years_count')
    def _compute_range(self):
        today = fields.Date.today()
        for rec in self:
            if rec.period_type == 'quarterly':
                current = (today.month - 1) // 3 + 1
            elif rec.period_type == 'monthly':
                current = today.month
            else:
                current = 1
            years = max(rec.years_count, 1)
            rec.min_key = today.year * 100 + current
            rec.max_key = (today.year + years - 1) * 100 + 99

    @api.depends('option_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.option_id.name or ''

    @api.depends('line_ids')
    def _compute_customer_count(self):
        for rec in self:
            rec.customer_count=len(rec.line_ids)

    @api.onchange('period_type', 'years_count')
    def _onchange_reset_option(self):
        self.option_id = False

    @api.onchange('select_all')
    def _onchange_select_all(self):
        for line in self.line_ids:
            if not line.added:
                line.selected = self.select_all

    @api.onchange('select_all_print')
    def _onchange_select_all_print(self):
        for req in self.request_ids:
            req.print_selected = self.select_all_print

    @api.onchange('date')
    def _onchange_date(self):
        # (1) تعديل التاريخ بيعدل تاريخ المطابقة في كل البنود
        if self.date:
            for req in self.request_ids:
                req.reconcile_date = self.date

    @api.onchange('company_id')
    def _onchange_company_id(self):
        # (2) لو المندوب مش تابع للشركة الجديدة نفضّي الحقل
        if self.user_id and self.user_id.partner_id.company_id != self.company_id:
            self.user_id = False

    def write(self, vals):
        # بيانات المطابقة مقفولة لما الحالة تبقى "منتهي"
        locked = {'years_count', 'period_type', 'option_id', 'date',
                  'company_id', 'user_id', 'balance_type_ids'}
        if locked & set(vals) and any(
                rec.state == 'done' for rec in self):
            raise UserError('مينفعش تعدل بيانات المطابقة وحالتها "منتهي".')
        old_dates = {}
        if 'date' in vals:
            old_dates = {rec.id: rec.date for rec in self}
        res = super().write(vals)
        if 'date' in vals:
            for rec in self:
                if rec.date and old_dates.get(rec.id) != rec.date \
                        and rec.request_ids:
                    rec.request_ids.write({'reconcile_date': rec.date})
        return res

    # (3) انتقالات الحالة
    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    @api.constrains('years_count')
    def _check_years_count(self):
        for rec in self:
            if rec.years_count < 1 or rec.years_count > 10:
                raise ValidationError('عدد السنين لازم يكون من 1 لـ 10.')

    def action_load_customers(self):
        self.ensure_one()
        codes = self.balance_type_ids.mapped('code')
        if not codes:
            raise UserError('اختار نوع العملاء الأول (سالب / موجب / صفر).')

        domain = [
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('partner_id', '!=', False),
        ]
        if self.user_id:
            domain.append(('partner_id.user_id', '=', self.user_id.id))

        groups = self.env['account.move.line']._read_group(
            domain, ['partner_id'], ['balance:sum'])

        # العملاء اللي اتضافوا قبل كده للفترة دي
        already_added = self.request_ids.mapped('partner_id').ids

        values = []
        for partner, balance in groups:
            balance = round(balance, 2)
            if balance > 0:
                kind = 'positive'
            elif balance < 0:
                kind = 'negative'
            else:
                kind = 'zero'
            if kind in codes:
                values.append((0, 0, {
                    'partner_id': partner.id,
                    'balance': balance,
                    'added': partner.id in already_added,
                }))

        self.line_ids.unlink()
        self.write({'line_ids': values, 'select_all': False})

    def action_add_selected(self):
        self.ensure_one()
        chosen = self.line_ids.filtered(lambda l: l.selected and not l.added)
        if not chosen:
            raise UserError('حدد عميل واحد على الأقل.')
        chosen.action_add()
        self.select_all = False

    def action_print_report(self):
        self.ensure_one()
        if not self.request_ids:
            raise UserError('مفيش بنود في "مطلوب مطابقة" للطباعة.')
        return self.env.ref(
            'reconciliation_period.action_report_salesperson'
        ).report_action(self)

    def get_print_requests(self):
        """(7) بنود المطابقة اللي هتتطبع: المحددة بس، ولو مفيش تحديد بتطلع الكل."""
        self.ensure_one()
        requests = self.request_ids
        selected = requests.filtered('print_selected')
        return selected or requests

    def get_salesperson_groups(self):
        """بيرجع طلبات المطابقة مجمعة حسب المندوب (للتقرير).

        - لو في بنود محددة للطباعة بتطلع هي بس، وإلا كل البنود.
        - لو المندوب متحدد في الفترة، التقرير بيطلع طلباته هو بس.
        - لو فاضي بيطلع كل المناديب، كل واحد لوحده.
        """
        self.ensure_one()
        groups = {}
        order = []
        for req in self.get_print_requests():
            if self.user_id and req.user_id != self.user_id:
                continue
            key = req.user_id.id or 0
            if key not in groups:
                groups[key] = {
                    'user': req.user_id,
                    'responsible': self.env['res.users'],
                    'supervisor': self.env['res.users'],
                    'requests': self.env['reconciliation.request'],
                    'total_current': 0.0,
                    'total_at_date': 0.0,
                    'total_customer': 0.0,
                    'total_difference': 0.0,
                }
                order.append(key)
            group = groups[key]
            group['requests'] += req
            # (6) مسئول المندوب والمشرف (أول قيمة موجودة في المجموعة)
            if not group['responsible'] and req.responsible_id:
                group['responsible'] = req.responsible_id
            if not group['supervisor'] and req.supervisor_id:
                group['supervisor'] = req.supervisor_id
            group['total_current'] += req.current_balance
            group['total_at_date'] += req.balance_at_date
            group['total_customer'] += req.customer_balance
            group['total_difference'] += req.difference
        return [groups[key] for key in order]


class ReconciliationPeriodLine(models.Model):
    _name = 'reconciliation.period.line'
    _description = 'Reconciliation Period Line'
    _order = 'id'

    period_id = fields.Many2one(
        'reconciliation.period', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='العميل')
    balance = fields.Float(string='الرصيد الحالي')
    selected = fields.Boolean(string='تحديد', default=False)
    added = fields.Boolean(string='تمت الإضافة', default=False)
    serial = fields.Integer(string='الرقم', compute='_compute_serial')

    @api.depends('period_id.line_ids')
    def _compute_serial(self):
        numbers = {}
        for period in self.mapped('period_id'):
            for index, line in enumerate(period.line_ids,start=1):
                numbers[line.id] = index
        for rec in self:
            rec.serial = numbers.get(rec.id, 0)
          
    def action_add(self):
        Request = self.env['reconciliation.request']
        for line in self:
            if line.added:
                continue
            partner = line.partner_id
            user = partner.user_id

            # فريق المبيعات: من العميل لو الحقل موجود، وإلا من فريق المندوب
            team = self.env['crm.team']
            if 'team_id' in partner._fields:
                team = partner.team_id
            elif user and 'sale_team_id' in user._fields:
                team = user.sale_team_id

            # حماية من التكرار: مفيش طلب تاني لنفس العميل في نفس الفترة
            exists = Request.search_count([
                ('period_id', '=', line.period_id.id),
                ('partner_id', '=', partner.id),
            ])
            if not exists:
                Request.create({
                    'period_id': line.period_id.id,
                    'partner_id': partner.id,
                    'partner_name': partner.name,
                    'user_id': user.id,
                    'team_id': team.id,
                    # (6) مسئول المندوب = قائد فريق المبيعات (وممكن يتعدل)
                    'responsible_id': team.user_id.id if team else False,
                    'company_id': line.period_id.company_id.id,
                    'current_balance': line.balance,
                    'reconcile_date': (
                        line.period_id.date or fields.Date.today()),
                })
            line.write({'added': True, 'selected': False})


class ReconciliationRequest(models.Model):
    _name = 'reconciliation.request'
    _description = 'Reconciliation Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    period_id = fields.Many2one(
        'reconciliation.period', string='الفترة',
        required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='العميل')

    # بيانات مخزنة: بتتنسخ وقت الإضافة ومبتتغيرش بعد كده
    partner_name = fields.Char(string='اسم العميل')
    user_id = fields.Many2one(
        'res.users', string='المندوب',
        domain="[('partner_id.company_id', '=', company_id)]")
    team_id = fields.Many2one('crm.team', string='فريق المبيعات')

    # (6) مسئول المندوب والمشرف
    responsible_id = fields.Many2one(
        'res.users', string='مسئول المندوب',
        domain="[('partner_id.company_id', '=', company_id)]")
    supervisor_id = fields.Many2one(
        'res.users', string='المشرف',
        domain="[('partner_id.company_id', '=', company_id)]")

    # (7) تحديد البند للطباعة
    print_selected = fields.Boolean(string='تحديد للطباعة', copy=False)

    current_balance = fields.Float(string='الرصيد الحالي')
    reconcile_date = fields.Date(
        string='تاريخ المطابقة', default=fields.Date.today)
    balance_at_date = fields.Float(
        string='رصيدنا يوم المطابقة',
        compute='_compute_balance_at_date', store=True)
    customer_balance = fields.Float(string='رصيد العميل (يدوي)')
    difference = fields.Float(
        string='الفرق', compute='_compute_difference', store=True)
    match_state = fields.Selection([
        ('matched', 'مطابق'),
        ('unmatched', 'غير مطابق'),
    ], string='الحالة', compute='_compute_difference', store=True)

    approved_accounts = fields.Boolean(
        string='معتمد حسابات', tracking=True, copy=False)
    approved_sales = fields.Boolean(
        string='معتمد مبيعات', tracking=True, copy=False)
    approved_papers = fields.Boolean(
        string='معتمد أوراق', tracking=True, copy=False)

    # (10) حالة التقرير: مسودة / منتهي (منتهي لما كل الاعتمادات تتم)
    approval_state = fields.Selection([
        ('draft', 'مسودة'),
        ('done', 'منتهي'),
    ], string='حالة التقرير', compute='_compute_approval_state',
        store=True, tracking=True)

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='الشركة',
        required=True,
        default=lambda self: self.env.company
    )

    # ملف PDF بتاع الأوراق
    papers_file = fields.Binary(string='ملف الأوراق (PDF)', attachment=True)
    papers_filename = fields.Char(string='اسم الملف')

    # @api.constrains('papers_file')
    # def _check_papers_pdf(self):
    #     for rec in self:
    #         if rec.papers_file:
    #             # بنفحص أول بايتات الملف نفسه (مش الاسم بس)
    #             header = base64.b64decode(rec.papers_file[:8])[:4]
    #             if header != b'%PDF':
    #                 raise ValidationError('ملف الأوراق لازم يكون PDF.')

    @api.depends('approved_accounts', 'approved_sales', 'approved_papers')
    def _compute_approval_state(self):
        for rec in self:
            if (rec.approved_accounts and rec.approved_sales
                    and rec.approved_papers):
                rec.approval_state = 'done'
            else:
                rec.approval_state = 'draft'

    # (8) أزرار الاعتماد
    def action_approve_sales(self):
        self.filtered(lambda r: not r.approved_sales).write(
            {'approved_sales': True})

    def action_approve_papers(self):
        self.filtered(lambda r: not r.approved_papers).write(
            {'approved_papers': True})

    def action_approve_accounts(self):
        self.filtered(lambda r: not r.approved_accounts).write(
            {'approved_accounts': True})

    def action_reset_approvals(self):
        self.write({
            'approved_sales': False,
            'approved_papers': False,
            'approved_accounts': False,
        })

    # (9) عرض ملف الـ PDF في الشات (chatter)
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if vals.get('papers_file'):
                rec._post_papers_file()
        return records

    def write(self, vals):
        # الحقول دي مقفولة لما حالة التقرير تبقى "منتهي"
        locked = {'partner_id', 'partner_name', 'user_id',
                  'company_id', 'current_balance'}
        if locked & set(vals) and any(
                rec.approval_state == 'done' for rec in self):
            raise UserError(
                'مينفعش تعدل العميل أو المندوب أو الشركة أو الرصيد الحالي '
                'والتقرير حالته "منتهي".')
        res = super().write(vals)
        if vals.get('papers_file'):
            self._post_papers_file()
        return res

    def _post_papers_file(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            if not rec.papers_file:
                continue
            name = rec.papers_filename or 'papers.pdf'
            if '.' not in name:
                name += '.pdf'
            attachment = Attachment.create({
                'name': name,
                'datas': rec.papers_file,
                'res_model': rec._name,
                'res_id': rec.id,
            })
            rec.message_post(
                body='تم رفع ملف الأوراق: %s' % name,
                attachment_ids=[attachment.id])
            if rec.period_id:
                rec.period_id.message_post(
                    body='تم رفع ملف الأوراق للعميل %s: %s' % (
                        rec.partner_name or '', name),
                    attachment_ids=[attachment.id])

    @api.onchange('company_id')
    def _onchange_company_id(self):
        for field in ('user_id', 'responsible_id', 'supervisor_id'):
            user = self[field]
            if user and user.partner_id.company_id != self.company_id:
                self[field] = False

    @api.depends('partner_id', 'reconcile_date')
    def _compute_balance_at_date(self):
        for rec in self:
            if not rec.partner_id or not rec.reconcile_date:
                rec.balance_at_date = 0.0
                continue
            domain = [
                ('account_id.account_type', '=', 'asset_receivable'),
                ('parent_state', '=', 'posted'),
                ('partner_id', '=', rec.partner_id.id),
                ('date', '<=', rec.reconcile_date),
            ]
            result = self.env['account.move.line']._read_group(
                domain, [], ['balance:sum'])
            total = result[0][0] if result else 0.0
            rec.balance_at_date = total or 0.0

    @api.depends('balance_at_date', 'customer_balance')
    def _compute_difference(self):
        for rec in self:
            diff = round(rec.balance_at_date - rec.customer_balance, 2)
            rec.difference = diff
            if diff == 0:
                rec.match_state = 'matched'
            else:
                rec.match_state = 'unmatched'
