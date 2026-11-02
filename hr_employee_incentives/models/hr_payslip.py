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
        if type == 'penalty':
            input_type_id = self.env.ref('hr_employee_incentives.payslip_input_type_penalty').id
            input_lines = self.input_line_ids.filtered(lambda l: l.input_type_id.id == input_type_id)
            for line in input_lines:
                penalty = self.env['employee.penalty'].browse(line.penalty_id.id)
                if action == 'discount':
                    penalty.action_discount()
                elif action == 'approve':
                    penalty.action_approve()

        elif type == 'reward':
            input_type_id = self.env.ref('hr_employee_incentives.payslip_input_type_reward').id
            input_lines = self.input_line_ids.filtered(lambda l: l.input_type_id.id == input_type_id)
            for line in input_lines:
                reward = self.env['employee.reward'].browse(line.reward_id.id)
                if action == 'paid':
                    reward.action_paid()
                elif action == 'approve':
                    reward.action_approve()

    def _incentive_amount(self, record):
        """قيمة الجزاء/المكافأة بالمبلغ: لو بالأيام تتحول إلى مبلغ حسب أجر العقد."""
        self.ensure_one()
        # مكافأة اتصرف جزء منها بدفعة: اللي بيدخل الكشف هو المتبقي بس
        if record._name == 'employee.reward' and record.disbursement_type == 'payment':
            return record.remaining_amount
        if record.apply_type == 'days':
            days = record.days or 0.0
            wage = self.contract_id.wage if self.contract_id else 0.0
            return days * wage / DAYS_IN_MONTH
        return record.amount or 0.0

    def _sync_incentive_inputs(self):
        """يعيد بناء سطور الجزاءات والمكافآت المعتمدة داخل الكشف حسب فترته، ويحدّث حالة مقبوضات الراتب."""
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
            # الجزاءات
            payslip.input_line_ids.filtered(lambda l: l.input_type_id == type_penalty).unlink()
            penalties = self.env['employee.penalty'].search(domain)
            for penalty in penalties:
                self.env['hr.payslip.input'].create({
                    'payslip_id': payslip.id,
                    'input_type_id': type_penalty.id,
                    'amount': payslip._incentive_amount(penalty),
                    'name': penalty.penalty_type_id.name,
                    'penalty_id': penalty.id,
                })
            # المكافآت
            payslip.input_line_ids.filtered(lambda l: l.input_type_id == type_reward).unlink()
            # المكافآت المصروفة بدفعة مش بتدخل الكشف، إلا لو فيه متبقي بعد الدفعات
            rewards = self.env['employee.reward'].search(
                domain + ['|', ('disbursement_type', '!=', 'payment'),
                          ('remaining_amount', '>', 0)])
            for reward in rewards:
                self.env['hr.payslip.input'].create({
                    'payslip_id': payslip.id,
                    'input_type_id': type_reward.id,
                    'amount': payslip._incentive_amount(reward),
                    'name': reward.reward_type_id.name,
                    'reward_id': reward.id,
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

    def compute_sheet(self):
        self._sync_incentive_inputs()
        return super().compute_sheet()

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
        return super().write(vals)
