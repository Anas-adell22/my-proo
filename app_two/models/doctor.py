from odoo import fields,models

class hospitaldoctor(models.Model):
    _name= 'hospital.doctor'
    _description = 'Hospital Doctor'

    name = fields.Char(string='Doctor name' , required = True)
    specialty = fields.Selection([
    ('cardiology', 'Cardiology'),
    ('neurology', 'Neurology'),
    ('pediatrics', 'Pediatrics'),
    ('orthopedics', 'Orthopedics'),
    ('general', 'General Medicine'),
    ('surgery', 'Surgery'),
], string='Specialty')

    patient_ids = fields.One2many('hospital.patient', 'doctor_id', string='Patients')
