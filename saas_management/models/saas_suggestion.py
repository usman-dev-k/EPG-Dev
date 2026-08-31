# -*- coding: utf-8 -*-
from odoo import models, fields

class SaasSuggestion(models.Model):
    _name = 'saas.suggestion'
    _description = 'Tenant Suggestion'
    _order = 'create_date desc'

    subscription_id = fields.Many2one('saas.subscription', string='Suscripción', ondelete='cascade')
    database_name = fields.Char(related='subscription_id.database_name', string='Base de datos', store=True)
    customer_id = fields.Many2one(related='subscription_id.partner_id', string='Cliente', store=True)
    email = fields.Char(string='Correo electrónico del remitente', required=True)
    suggestion_text = fields.Text(string='Sugerencia', required=True)
    state = fields.Selection([
        ('new', 'Nuevo'),
        ('reviewed', 'Revisado'),
        ('resolved', 'Resuelto')
    ], string='Estado', default='new', tracking=True)
