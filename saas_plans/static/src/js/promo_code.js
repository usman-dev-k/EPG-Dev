/* SaaS Custom Promo Code Handler */
/* Handles custom promo code UI with apply and remove functionality */

(function () {
    'use strict';

    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPromoHandler);
    } else {
        initPromoHandler();
    }

    function initPromoHandler() {
        console.log('[SaaS Promo] Initializing custom promo code handler');

        // Hide System's default promo code form
        const defaultPromoForm = document.querySelector('form[name="coupon_code"]');
        if (defaultPromoForm) {
            defaultPromoForm.style.display = 'none';
            console.log('[SaaS Promo] Hidden default promo code form');
        }

        // Get UI elements
        const promoInput = document.querySelector('.promo-code-input');
        const applyBtn = document.querySelector('.apply-promo-btn');
        const removeBtn = document.querySelector('.remove-promo-btn');
        const promoMessage = document.querySelector('.promo-message');

        // Apply promo code
        if (applyBtn && promoInput) {
            applyBtn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation(); // Prevent System from interpreting this as address selection
                applyPromoCode();
            });

            // Also allow Enter key
            promoInput.addEventListener('keypress', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    e.stopPropagation();
                    applyPromoCode();
                }
            });

            // Prevent clicks on input from bubbling too
            promoInput.addEventListener('click', function (e) {
                e.stopPropagation();
            });
        }

        // Remove promo code
        if (removeBtn) {
            removeBtn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation(); // Prevent System from interpreting this as address selection
                removePromoCode();
            });
        }

        function applyPromoCode() {
            const promoCode = promoInput.value.trim();
            if (!promoCode) {
                showMessage('Please enter a promo code', 'danger');
                return;
            }

            // Disable button during request
            applyBtn.disabled = true;
            applyBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Applying...';

            // Make AJAX request to custom endpoint
            fetch('/saas/apply_promo_code', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {
                        promo_code: promoCode
                    }
                })
            })
                .then(response => response.json())
                .then(data => {
                    const result = data.result || data;

                    if (result.success) {
                        showMessage(result.message, 'success');
                        // Reload page to show updated UI and totals
                        setTimeout(() => {
                            window.location.reload();
                        }, 1000);
                    } else {
                        showMessage(result.message || 'Invalid promo code', 'danger');
                        applyBtn.disabled = false;
                        applyBtn.innerHTML = '<i class="fa fa-check"></i> Apply';
                    }
                })
                .catch(error => {
                    console.error('[SaaS Promo] Error applying promo code:', error);
                    showMessage('An error occurred. Please try again.', 'danger');
                    applyBtn.disabled = false;
                    applyBtn.innerHTML = '<i class="fa fa-check"></i> Apply';
                });
        }

        function removePromoCode() {
            if (!confirm('Remove this promo code?')) {
                return;
            }

            // Disable button during request
            removeBtn.disabled = true;
            removeBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Removing...';

            // Make AJAX request to remove endpoint
            fetch('/saas/remove_promo_code', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {}
                })
            })
                .then(response => response.json())
                .then(data => {
                    const result = data.result || data;

                    if (result.success) {
                        // Reload page to show updated UI and totals
                        window.location.reload();
                    } else {
                        alert(result.message || 'Error removing promo code');
                        removeBtn.disabled = false;
                        removeBtn.innerHTML = '<i class="fa fa-times"></i> Remove';
                    }
                })
                .catch(error => {
                    console.error('[SaaS Promo] Error removing promo code:', error);
                    alert('An error occurred. Please try again.');
                    removeBtn.disabled = false;
                    removeBtn.innerHTML = '<i class="fa fa-times"></i> Remove';
                });
        }

        function showMessage(message, type) {
            if (!promoMessage) return;

            promoMessage.textContent = message;
            promoMessage.className = `promo-message alert alert-${type} mt-2`;
            promoMessage.style.display = 'block';

            // Auto-hide success messages after 3 seconds
            if (type === 'success') {
                setTimeout(() => {
                    promoMessage.style.display = 'none';
                }, 3000);
            }
        }
    }
})();
