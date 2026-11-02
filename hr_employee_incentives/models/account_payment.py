from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    grievance_id = fields.Many2one('hr.grievance', string='التظلم', copy=False, index=True,
                                   ondelete='set null')

    petition_id = fields.Many2one('hr.petition', string='الالتماس', copy=False, index=True,
                                  ondelete='set null')

    reward_id = fields.Many2one('employee.reward', string='المكافأة', copy=False, index=True,
                                ondelete='set null')

    def _sync_reward_payments(self):
        """تحديث المكافأة المرتبطة (الحالة + تسجيل المتبقي في مقبوضات الراتب)."""
        rewards = self.filtered('reward_id').mapped('reward_id')
        if rewards:
            rewards._sync_payment_state()

    @api.depends('move_id.state', 'move_id.payment_state')
    def _compute_state(self):
        super()._compute_state()
        # بعد تغيّر حالة الدفعة نحدّث حالة المكافأة المرتبطة (معتمد / تم الصرف)
        self._sync_reward_payments()

    # بنربط التحديث بأزرار الدفعة نفسها كمان، عشان المتبقي يتسجل فور التأكيد
    def action_post(self):
        res = super().action_post()
        self._sync_reward_payments()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        self._sync_reward_payments()
        return res

    def action_draft(self):
        res = super().action_draft()
        self._sync_reward_payments()
        return res
