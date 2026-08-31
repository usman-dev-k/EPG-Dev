from odoo import models, fields, api
from odoo.exceptions import UserError

class SaasTrainingVideo(models.Model):
    _name = 'saas.training.video'
    _description = 'Training Video'
    _order = 'sequence, id'

    name = fields.Char('Título', required=True)
    sequence = fields.Integer(default=10, string="Secuencia")
    category = fields.Selection([
        ('sales', 'Ventas'),
        ('accounting', 'Contabilidad'),
        ('pipeline', 'Flujo'),
        ('general', 'General')
    ], string='Categoría', required=True, default='general')
    video_url = fields.Char('Enlace de YouTube', required=True)
    description = fields.Text(string='Descripción')

    def action_open_video(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.video_url,
            'target': 'new',
        }

    def action_push_to_tenants(self):
        if 'saas.subscription' in self.env:
            self.env['saas.subscription'].sync_training_videos(self)
        else:
            raise UserError('Esta acción solo está disponible en la base de datos maestra.')
