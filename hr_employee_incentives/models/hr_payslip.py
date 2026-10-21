# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# عدد أيام الشهر المستخدم لتحويل "أيام" الجزاء/المكافأة إلى مبلغ (اليومية = الأجر ÷ هذا الرقم)
DAYS_IN_MONTH = 30

class InputLineIncentive(models.Model):
    _inherit = 'hr.payslip.input'
    penalty_id = fields.Many2one('employee.penalty', ondelete='set null')
    reward_id = fields.Many2one('employee.reward', ondelete='set null')


class HrPayslipIncentive(models.Model):
    _inherit = 'hr.payslip'

    def _change_incentive_state(self, action, type):
        """يغيّر حالة الجزاءات/المكافآت المرتبطة بالكشف (عن طريق مقبوضات الراتب)."""
        model_name = 'employee.penalty' if type == 'penalty' else 'employee.reward'
        for payslip in self:
            receipts = self.env['payroll.receipt'].sudo().search([
                ('payslip_id', '=', payslip.id),
                ('source_model', '=', model_name),
                ('state', '=', 'included'),
            ])
            records = self.env[model_name].browse(receipts.mapped('source_id')).exists()
            for record in records:
                if action == 'discount':
                    record.action_discount()
                elif action == 'paid':
                    record.action_paid()
                elif action == 'approve':
                    record.action_approve()

    def _incentive_amount(self, record):
        """قيمة الجزاء/المكافأة بالمبلغ: لو بالأيام تتحول إلى مبلغ حسب أجر العقد."""
        self.ensure_one()
        if record.apply_type == 'days':
            days = record.days or 0.0
            wage = self.contract_id.wage if self.contract_id else 0.0
            return days * wage / DAYS_IN_MONTH
        return record.amount or 0.0

    def _sync_incentive_inputs(self):
        """يبني سطر input واحد لكل نوع (جزاءات / مكافآت) بإجمالي الشهر، ويحدّث مقبوضات الراتب.

        سطر واحد لكل كود لأن قواعد الراتب تقرأ `inputs['CODE']` وهي تحتفظ بسطر واحد فقط لكل كود.
        """
        type_penalty = self.env.ref('hr_employee_incentives.payslip_input_type_penalty')
        type_reward = self.env.ref('hr_employee_incentives.payslip_input_type_reward')
        receipt_model = self.env['payroll.receipt'].sudo()
        for payslip in self.filtered(lambda p: p.state in ('draft', 'verify')):
            if not (payslip.employee_id and payslip.date_from and payslip.date_to):
                continue
            domain = [
                ('employee_id', '=', payslip.employee_id.id),
                ('state', '=', 'approved'),
                ('date', '>=', payslip.date_from),
                ('date', '<=', payslip.date_to),
            ]
            penalties = self.env['employee.penalty'].search(domain)
            rewards = self.env['employee.reward'].search(domain + [('disbursement_type', '!=', 'payment')])
            for input_type, records, name_field in (
                (type_penalty, penalties, 'penalty_type_id'),
                (type_reward, rewards, 'reward_type_id'),
            ):
                payslip.input_line_ids.filtered(lambda l: l.input_type_id == input_type).unlink()
                if not records:
                    continue
                names = list(dict.fromkeys(records.mapped(name_field + '.name')))
                self.env['hr.payslip.input'].create({
                    'payslip_id': payslip.id,
                    'input_type_id': input_type.id,
                    'amount': sum(payslip._incentive_amount(r) for r in records),
                    'name': '، '.join(names),
                })
            # مقبوضات الراتب: ما دخل الكشف = "داخل كشف المرتب"، وما خرج منه يرجع "معلّق"
            keys = {('employee.penalty', p.id) for p in penalties} | {('employee.reward', r.id) for r in rewards}
            old = receipt_model.search([('payslip_id', '=', payslip.id), ('state', '=', 'included')])
            old.filtered(lambda r: (r.source_model, r.source_id) not in keys).write(
                {'state': 'pending', 'payslip_id': False})
            for model_name, ids in (('employee.penalty', penalties.ids), ('employee.reward', rewards.ids)):
                if ids:
                    receipt_model.search([
                        ('source_model', '=', model_name),
                        ('source_id', 'in', ids),
                        ('state', '!=', 'cancelled'),
                    ]).write({'state': 'included', 'payslip_id': payslip.id})

    def _split_incentive_lines(self):
        """يقسّم سطر الجزاءات/المكافآت في الإيصال إلى سطر لكل سجل (مجموعها = قيمة السطر الأصلي)."""
        receipt_model = self.env['payroll.receipt'].sudo()
        for payslip in self.filtered(lambda p: p.state in ('draft', 'verify')):
            for code, model_name, name_field in (
                ('DEDUCTION', 'employee.penalty', 'penalty_type_id'),
                ('REWARD', 'employee.reward', 'reward_type_id'),
            ):
                lines = payslip.line_ids.filtered(lambda l: l.salary_rule_id.code == code)
                if len(lines) != 1:
                    if len(lines) > 1:
                        _logger.warning('الكشف %s فيه أكثر من سطر بالكود %s، لن يتم تقسيمه', payslip.display_name, code)
                    continue
                receipts = receipt_model.search([
                    ('payslip_id', '=', payslip.id),
                    ('source_model', '=', model_name),
                    ('state', '=', 'included'),
                ])
                records = self.env[model_name].browse(receipts.mapped('source_id')).exists()
                records = records.sorted(lambda r: (r.date, r.id))
                if len(records) < 2 or not lines.amount:
                    continue
                try:
                    with self.env.cr.savepoint():
                        sign = -1 if lines.amount < 0 else 1
                        amounts = [round(sign * payslip._incentive_amount(r), 2) for r in records]
                        amounts[-1] = round(lines.amount - sum(amounts[:-1]), 2)  # يحافظ على الإجمالي بدقة
                        for index, (record, amount) in enumerate(zip(records, amounts)):
                            vals = {
                                'name': record[name_field].name,
                                'amount': amount,
                                # الإجمالي يتحدد صراحةً حتى لا يفضل بقيمة السطر الأصلي
                                'total': amount * lines.quantity * lines.rate / 100.0,
                            }
                            if index == 0:
                                lines.write(vals)
                            else:
                                lines.copy(vals)
                except Exception:
                    _logger.warning('تعذر تقسيم سطر %s في الكشف %s', code, payslip.display_name, exc_info=True)

    def compute_sheet(self):
        self._sync_incentive_inputs()
        res = super().compute_sheet()
        self._split_incentive_lines()
        return res

    def action_payslip_unpaid(self):
        res = super().action_payslip_unpaid()
        self._change_incentive_state('approve', 'penalty')
        self._change_incentive_state('approve', 'reward')
        return res

    def write(self, vals):
        if 'state' in vals:
            if vals['state'] == 'paid':
                self._change_incentive_state('discount', 'penalty')
                self._change_incentive_state('paid', 'reward')
            if vals['state'] == 'cancel':
                self._change_incentive_state('approve', 'penalty')
                self._change_incentive_state('approve', 'reward')
                self.env['payroll.receipt'].sudo().search([
                    ('payslip_id', 'in', self.ids), ('state', '=', 'included'),
                ]).write({'state': 'pending', 'payslip_id': False})
        return super().write(vals)
