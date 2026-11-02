# -*- coding: utf-8 -*-
def migrate(cr, version):
    """نقل القيم القديمة (computed_amount كانت بتيجي من البنود) إلى الحقول الجديدة القابلة للتعديل."""
    for table in ('employee_penalty', 'employee_reward'):
        cr.execute("""SELECT 1 FROM information_schema.columns
                      WHERE table_name = %s AND column_name = 'computed_amount'""", (table,))
        if not cr.fetchone():
            continue
        cr.execute("""UPDATE {t} SET days = computed_amount
                      WHERE apply_type = 'days' AND COALESCE(days, 0) = 0
                        AND COALESCE(computed_amount, 0) > 0""".format(t=table))
        cr.execute("""UPDATE {t} SET amount = computed_amount
                      WHERE apply_type = 'amount' AND COALESCE(amount, 0) = 0
                        AND COALESCE(computed_amount, 0) > 0""".format(t=table))
