/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.SaasRegistrationCheck = publicWidget.Widget.extend({
    selector: '.oe_website_sale',
    events: {
        'focusout input[name="email"], focusout input[name="login"]': '_onEmailChange',
        'input input[name="email"], input input[name="login"]': '_onEmailInput',
        'click .a-submit, click #save_address, click button[type="submit"]': '_onButtonClick',
        'submit form': '_onFormSubmit',
    },

    init: function () {
        this._super.apply(this, arguments);
        this.emailValid = true;
    },

    _toggleSubmitButton: function (disabled) {
        const $btns = this.$('.a-submit, #save_address, button[type="submit"]');
        if (disabled) {
            $btns.addClass('disabled').attr('disabled', 'disabled').css('opacity', '0.5');
        } else {
            $btns.removeClass('disabled').removeAttr('disabled').css('opacity', '1');
        }
    },

    _onEmailInput: function (ev) {
        const $input = $(ev.currentTarget);
        $input.removeClass('is-invalid');
        $input.parent().find('.saas-email-error').remove();
        this.emailValid = true;
        this._toggleSubmitButton(false);
    },

    _onEmailChange: async function (ev) {
        const $input = $(ev.currentTarget);
        const email = $input.val().trim();
        
        $input.parent().find('.saas-email-error').remove();

        if (!email || !email.includes('@')) {
            this.emailValid = true;
            this._toggleSubmitButton(false);
            return;
        }

        // Disable button while checking
        this._toggleSubmitButton(true);

        try {
            const result = await rpc('/saas/check_email_availability', { email: email });
            
            if (!result.available) {
                this.emailValid = false;
                $input.addClass('is-invalid');
                $input.after(`<div class="saas-email-error invalid-feedback d-block" style="color: #dc3545; font-weight: 500; margin-top: 5px;">${result.message}</div>`);
                this._toggleSubmitButton(true); // Keep disabled if taken
            } else {
                this.emailValid = true;
                $input.removeClass('is-invalid');
                this._toggleSubmitButton(false); // Enable if available
            }
        } catch (error) {
            console.error("SaaS: Email check failed", error);
            this._toggleSubmitButton(false);
        }
    },

    _onButtonClick: function (ev) {
        if (!this.emailValid) {
            ev.preventDefault();
            ev.stopPropagation();
            alert(_t("Please use a different email address to continue. This one is already registered."));
            return false;
        }
    },

    _onFormSubmit: function (ev) {
        if (!this.emailValid) {
            ev.preventDefault();
            return false;
        }
    },
});
