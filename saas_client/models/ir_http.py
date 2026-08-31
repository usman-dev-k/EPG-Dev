# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request
from werkzeug.utils import redirect
import logging

_logger = logging.getLogger(__name__)

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    # ---------------------------------------------------------------------------
    # Any URL whose path contains one of these SEGMENTS (split by '/') is blocked.
    # This catches  /odoo/system-parameters  AND  /odoo/crm/system-parameters
    # AND  /odoo/system-parameters/edit/5  etc.
    # ---------------------------------------------------------------------------
    SAAS_RESTRICTED_SEGMENTS = {
        'system-parameters',    # ir.config_parameter
        'apps',                 # module installer  (/odoo/apps)
        'website',              # website builder   (/odoo/website)
        'menus',                # menu items        (/odoo/menus)
    }

    # ---------------------------------------------------------------------------
    # Full path prefixes that are blocked regardless of segment logic.
    # Kept as a secondary safety net for well-known fixed routes.
    # ---------------------------------------------------------------------------
    SAAS_RESTRICTED_PREFIXES = [
        '/web/apps',
        '/web/website',
    ]

    # ---------------------------------------------------------------------------
    # action-* tokens (numeric ids or xml-ids) that are blocked.
    # Used when the URL is  /odoo/action-<token>  (or nested like /odoo/crm/action-30).
    # ---------------------------------------------------------------------------
    SAAS_RESTRICTED_ACTION_XMLIDS = {
        'base_setup.action_general_configuration',
        'base.action_ui_menu',
        'base.ir_ui_menu_action',
        'base.action_ir_config_parameter_form',
        'base.base_automation.base_automation_act',
        'base.action_server_action_form',
        'base.ir_sequence_form',
        'base.ir_cron_act',
        'base.action_res_groups_tree_each_form',
        'base.ir_access_form',
        'base.ir_rule_form',
    }

    SAAS_RESTRICTED_ACTION_IDS = {'1', '2', '30'}

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    @classmethod
    def _path_has_restricted_segment(cls, path):
        """
        Split the URL path by '/' and check whether ANY segment matches a
        restricted keyword.

        Examples that are all caught:
            /odoo/system-parameters
            /odoo/crm/system-parameters
            /odoo/system-parameters/edit/5
            /odoo/crm/system-parameters/edit/5
            /odoo/apps
            /odoo/crm/apps
        """
        segments = set(path.strip('/').split('/'))
        return bool(segments & cls.SAAS_RESTRICTED_SEGMENTS)

    @classmethod
    def _path_has_restricted_action(cls, path):
        """
        Check every segment of the path for the pattern  'action-<token>'
        and return True if that token is blocked.

        Catches both:
            /odoo/action-30
            /odoo/crm/action-30
            /odoo/action-base.action_ir_config_parameter_form

        Using a catch-all: every action-* segment is blocked because
        tenants should not access any technical actions directly via URL.
        Remove the catch-all `return True` at the bottom and rely only on the
        explicit sets if you need to whitelist some actions later.
        """
        for segment in path.strip('/').split('/'):
            if not segment.startswith('action-'):
                continue
            token = segment[len('action-'):]   # everything after "action-"
            if token in cls.SAAS_RESTRICTED_ACTION_IDS:
                return True
            if token in cls.SAAS_RESTRICTED_ACTION_XMLIDS:
                return True
            # Catch-all: block ANY action-* segment
            return True
        return False

    # ---------------------------------------------------------------------------
    # Main dispatch override
    # ---------------------------------------------------------------------------

    @classmethod
    def _dispatch(cls, endpoint):
        """Override _dispatch to enforce SaaS tenant restrictions."""
        try:
            if hasattr(request, 'httprequest'):
                path = request.httprequest.path

                # --------------------------------------------------------------
                # 0. Bypass redirects for JSON-RPC and specific frontend paths to avoid parse errors
                # --------------------------------------------------------------
                bypass_paths = ('/jsonrpc', '/web/dataset/call_kw', '/web/session/', '/web/webclient/translations', '/website/translations', '/web/static', '/website/static')
                
                if request.httprequest.mimetype == 'application/json' or any(path.startswith(bp) for bp in bypass_paths):
                    return super(IrHttp, cls)._dispatch(endpoint)


                # --------------------------------------------------------------
                # 1. Fixed prefix block (legacy / web routes)
                # --------------------------------------------------------------
                for rp in cls.SAAS_RESTRICTED_PREFIXES:
                    if path == rp or path.startswith(rp + '/'):
                        _logger.info("SaaS: blocked restricted prefix '%s'", path)
                        return redirect('/odoo')

                # --------------------------------------------------------------
                # 2. Segment-based block  — catches nested paths like
                #    /odoo/crm/system-parameters  or  /odoo/sale/apps
                # --------------------------------------------------------------
                if cls._path_has_restricted_segment(path):
                    _logger.info("SaaS: blocked restricted segment in '%s'", path)
                    return redirect('/odoo')

                # --------------------------------------------------------------
                # 3. Action-URL block  — catches /odoo/action-30 AND
                #    nested variants like /odoo/crm/action-30
                # --------------------------------------------------------------
                if cls._path_has_restricted_action(path):
                    _logger.info("SaaS: blocked restricted action URL '%s'", path)
                    return redirect('/odoo')

                # --------------------------------------------------------------
                # 4. Strip debug mode from query string
                # --------------------------------------------------------------
                if 'debug' in request.httprequest.args:
                    query_args = request.httprequest.args.copy()
                    query_args.pop('debug', None)
                    from werkzeug.urls import url_encode
                    qs = url_encode(query_args)
                    new_url = path + ('?' + qs if qs else '')
                    if hasattr(request, 'session') and getattr(request.session, 'debug', False):
                        request.session.debug = ''
                    return redirect(new_url)

                # Strip debug from session even when not in URL
                if hasattr(request, 'session') and getattr(request.session, 'debug', False):
                    request.session.debug = ''

                # --------------------------------------------------------------
                # 5. Subscription suspended check
                # --------------------------------------------------------------
                if not path.startswith('/web/static'):
                    status = request.env['ir.config_parameter'].sudo().get_param(
                        'saas.subscription_status', 'active'
                    )
                    if status == 'suspended' and not path.startswith('/suspended'):
                        return redirect('/suspended')

        except Exception as e:
            _logger.warning("SaaS _dispatch: check failed for path '%s': %s",
                            getattr(request.httprequest, 'path', '?'), e)

        return super(IrHttp, cls)._dispatch(endpoint)