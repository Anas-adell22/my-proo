from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    grievance_id = fields.Many2one('hr.grievance', string='التظلم', copy=False, index=True,
                                   ondelete='set null')

    petition_id = fields.Many2one('hr.petition', string='الالتماس', copy=False, index=True,
                                  ondelete='set null')

    reward_id = fields.Many2one('employee.reward', string='المكافأة', copy=False, index=True,
                                ondelete='set null')

    @api.depends('move_id.state', 'move_id.payment_state')
    def _compute_state(self):
        super()._compute_state()
        # بعد تغيّر حالة الدفعة نحدّث حالة المكافأة المرتبطة (معتمد / تم الصرف)
        self.filtered('reward_id').mapped('reward_id')._sync_payment_state()
