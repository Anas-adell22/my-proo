/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

patch(ListRenderer.prototype, {
    getColumns(record) {
        const cols = super.getColumns(record);

        const field = cols.find(c => c.name === "value");
        if (field && record?.data?.deduction_type) {
            field.label = record.data.deduction_type === "days" ? "الأيام" : "المبلغ";
        }

        if (field && record?.data?.reward_type) {
            field.label = record.data.reward_type === "days" ? "الأيام" : "المبلغ";
        }

        return cols;
    },
});