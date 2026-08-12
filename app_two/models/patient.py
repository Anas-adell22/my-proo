from odoo import models,fields, api
from odoo.exceptions import ValidationError
from datetime import date

class HospitalPatient(models.Model):
    _name = 'hospital.patient'
    _description = 'Hospital Patient Record'

    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Patient Name', required=True)
    
    # تحويل حقل العمر إلى compute وحفظه في قاعدة البيانات
    age = fields.Integer(string='Age', compute='_compute_age', store=True,readonly=True)
    
    national_id = fields.Char(string='ID', required=True)
    room_num = fields.Integer(string='Room_number', required=True, tracking=True)
    phone = fields.Char(string='Phone Number', tracking=True)
    address = fields.Text(string='Address')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
    ], string='Gender', default='male')
    Blood_type = fields.Selection([
        ('a-', 'A-'), ('a+', 'A+'),
        ('b-', 'B-'), ('b+', 'B+'),
        ('o-', 'O-'), ('o+', 'O+'),
        ('ab-', 'AB-'), ('ab+', 'AB+'),
    ], string='Blood type', default='a+')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('admitted', 'Admitted'),
        ('under_treatment', 'Under_Treatment'),
        ('discharged', 'Discharged'),
    ], string='state', default='draft', tracking=True)
    date = fields.Date(
        string="Date_tod", 
        default=fields.Date.context_today,
        required=True, 
        tracking=True
    )
    notes = fields.Text(string='Notes')
    doctor_id = fields.Many2one('hospital.doctor', string='Doctor')

    def action_admit(self):
        for rec in self:
            rec.state = 'admitted'

    def action_start_treatment(self):
        for rec in self:
            rec.state = 'under_treatment'

    def action_discharge(self):
        for rec in self:
            rec.state = 'discharged'

    # دالة حساب العمر تلقائياً بناءً على الرقم القومي المصري
    @api.depends('national_id')
    def _compute_age(self):
        for rec in self:
            if rec.national_id and len(rec.national_id) == 14 and rec.national_id.isdigit():
                try:
                    century_digit = rec.national_id[0]
                    year_digits = int(rec.national_id[1:3])
                    month = int(rec.national_id[3:5])
                    day = int(rec.national_id[5:7])

                    if century_digit == '2':
                        birth_year = 1900 + year_digits
                    elif century_digit == '3':
                        birth_year = 2000 + year_digits
                    else:
                        rec.age = 0
                        continue

                    birth_date = date(birth_year, month, day)
                    today = date.today()
                    calculated_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                    rec.age = max(0, calculated_age)
                except ValueError:
                    rec.age = 0
            else:
                rec.age = 0

    # الـ Constraints الخاصة بالتحقق من صحة الرقم القومي
    @api.constrains('national_id')
    def _check_national_id(self):
        for rec in self:
            if not rec.national_id or not rec.national_id.isdigit():
                raise ValidationError('Please enter your 14-digit id number')
            if len(rec.national_id) != 14:
                raise ValidationError("National_id must be 14-digits")

    _sql_constraints = [
        ('unique_id_and_name', 'UNIQUE(national_id, name)', 'The ID and Name must be unique!')
    ]
