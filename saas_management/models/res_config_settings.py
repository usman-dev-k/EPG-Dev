from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    saas_promo_re_start = fields.Datetime(
        string="Real Estate Promo Start", 
        config_parameter='saas.promo_re_start'
    )
    saas_promo_re_end = fields.Datetime(
        string="Real Estate Promo End", 
        config_parameter='saas.promo_re_end'
    )