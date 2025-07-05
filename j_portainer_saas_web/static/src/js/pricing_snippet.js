/* ========================================================================== */
/* SAAS PRICING SNIPPET JAVASCRIPT */
/* Interactive functionality for pricing cards and billing toggle */
/* ========================================================================== */

odoo.define('j_portainer_saas_web.pricing_snippet', function (require) {
    'use strict';

    var core = require('web.core');
    var ajax = require('web.ajax');
    var publicWidget = require('web.public.widget');
    var _t = core._t;

    /**
     * SaaS Pricing Snippet Widget
     * Handles dynamic loading of packages, billing toggle, and user interactions
     */
    var SaaSPricingSnippet = publicWidget.Widget.extend({
        selector: '.saas-pricing-section',
        events: {
            'change .toggle-input': '_onBillingToggle',
            'click .btn-main': '_onBuyNowClick',
            'click .btn-trial': '_onFreeTrialClick',
            'click .saas-pricing-card': '_onCardClick',
        },

        /**
         * Initialize the widget
         */
        init: function () {
            this._super.apply(this, arguments);
            this.packages = [];
            this.currentBilling = 'monthly';
            this.freeTrialDays = 30;
            this._loadPackages();
        },

        /**
         * Widget ready - apply dynamic styling
         */
        start: function () {
            this._super.apply(this, arguments);
            this._applyDynamicStyling();
            return this._loadPackages();
        },

        /**
         * Load packages data from server
         * @private
         */
        _loadPackages: function () {
            var self = this;
            
            return ajax.jsonRpc('/saas/packages/data', 'call', {}).then(function (result) {
                if (result.success) {
                    self.packages = result.packages;
                    self.freeTrialDays = result.free_trial_days;
                    self._renderPackages();
                } else {
                    self._showError(result.error || 'Failed to load packages');
                }
            }).catch(function (error) {
                console.error('Error loading packages:', error);
                self._showError('Failed to load packages. Please try again.');
            });
        },

        /**
         * Render packages in the pricing cards
         * @private
         */
        _renderPackages: function () {
            var self = this;
            var $container = this.$('#pricingCards');
            
            // Clear loading spinner
            $container.empty();
            
            if (this.packages.length === 0) {
                $container.html('<div class="col-12 text-center"><p>No packages available at the moment.</p></div>');
                return;
            }

            // Create cards for each package
            this.packages.forEach(function (pkg, index) {
                var $card = self._createPackageCard(pkg, index);
                $container.append($card);
            });

            // Update pricing display
            this._updatePricingDisplay();
        },

        /**
         * Create a single package card
         * @param {Object} pkg - Package data
         * @param {number} index - Package index
         * @returns {jQuery} Card element
         * @private
         */
        _createPackageCard: function (pkg, index) {
            var isFeatured = index === 1; // Make second package featured
            var cardClass = 'col-lg-4 col-md-6 mb-4';
            
            var $card = $('<div>').addClass(cardClass);
            var $cardInner = $('<div>').addClass('saas-pricing-card h-100');
            
            if (isFeatured) {
                $cardInner.addClass('featured');
            }
            
            $cardInner.attr('data-package-id', pkg.id);
            
            // Card header
            var $header = $('<div>').addClass('card-header');
            $header.append($('<h3>').addClass('package-name').text(pkg.name));
            
            var $priceDisplay = $('<div>').addClass('price-display');
            $priceDisplay.append($('<span>').addClass('currency-symbol').text(pkg.currency_symbol));
            $priceDisplay.append($('<span>').addClass('price-amount').attr('data-monthly', pkg.monthly_price).attr('data-yearly', pkg.yearly_price));
            $priceDisplay.append($('<span>').addClass('price-period'));
            
            $header.append($priceDisplay);
            $cardInner.append($header);
            
            // Card body
            var $body = $('<div>').addClass('card-body');
            
            if (pkg.description) {
                $body.append($('<div>').addClass('package-description').text(pkg.description));
            }
            
            var $featuresList = $('<ul>').addClass('features-list');
            pkg.features.forEach(function (feature) {
                $featuresList.append($('<li>').text(feature));
            });
            $body.append($featuresList);
            
            $cardInner.append($body);
            
            // Card footer
            var $footer = $('<div>').addClass('card-footer');
            
            // Main button
            var $mainBtn = $('<button>').addClass('btn btn-primary btn-main').attr('data-action', 'buy');
            $mainBtn.append($('<span>').addClass('btn-text').text('Buy Now'));
            $mainBtn.append($('<i>').addClass('fa fa-arrow-right btn-icon'));
            $footer.append($mainBtn);
            
            // Free trial button
            if (pkg.has_free_trial) {
                var $trialBtn = $('<button>').addClass('btn btn-outline-secondary btn-trial').attr('data-action', 'trial');
                $trialBtn.append($('<span>').addClass('btn-text').text('Free Trial'));
                $trialBtn.append($('<i>').addClass('fa fa-gift btn-icon'));
                $footer.append($trialBtn);
            }
            
            $cardInner.append($footer);
            $card.append($cardInner);
            
            return $card;
        },

        /**
         * Update pricing display based on current billing period
         * @private
         */
        _updatePricingDisplay: function () {
            var self = this;
            var isYearly = this.currentBilling === 'yearly';
            
            this.$('.saas-pricing-card').each(function () {
                var $card = $(this);
                var $priceAmount = $card.find('.price-amount');
                var $pricePeriod = $card.find('.price-period');
                
                var monthlyPrice = parseFloat($priceAmount.attr('data-monthly')) || 0;
                var yearlyPrice = parseFloat($priceAmount.attr('data-yearly')) || 0;
                
                if (isYearly) {
                    $priceAmount.text(Math.round(yearlyPrice));
                    $pricePeriod.text('/ year');
                } else {
                    $priceAmount.text(Math.round(monthlyPrice));
                    $pricePeriod.text('/ month');
                }
            });
            
            // Update toggle labels
            this.$('.toggle-label').removeClass('active');
            this.$('.toggle-label[data-period="' + this.currentBilling + '"]').addClass('active');
        },

        /**
         * Handle billing toggle change
         * @param {Event} ev - Change event
         * @private
         */
        _onBillingToggle: function (ev) {
            var isChecked = $(ev.currentTarget).prop('checked');
            this.currentBilling = isChecked ? 'monthly' : 'yearly';
            this._updatePricingDisplay();
        },

        /**
         * Handle buy now button click
         * @param {Event} ev - Click event
         * @private
         */
        _onBuyNowClick: function (ev) {
            ev.preventDefault();
            var $card = $(ev.currentTarget).closest('.saas-pricing-card');
            var packageId = parseInt($card.attr('data-package-id'));
            
            this._selectPackage(packageId, false);
        },

        /**
         * Handle free trial button click
         * @param {Event} ev - Click event
         * @private
         */
        _onFreeTrialClick: function (ev) {
            ev.preventDefault();
            var $card = $(ev.currentTarget).closest('.saas-pricing-card');
            var packageId = parseInt($card.attr('data-package-id'));
            
            this._selectPackage(packageId, true);
        },

        /**
         * Handle card click for highlighting
         * @param {Event} ev - Click event
         * @private
         */
        _onCardClick: function (ev) {
            // Remove active class from all cards
            this.$('.saas-pricing-card').removeClass('active');
            // Add active class to clicked card
            $(ev.currentTarget).addClass('active');
        },

        /**
         * Handle package selection
         * @param {number} packageId - Package ID
         * @param {boolean} freeTrial - Whether free trial is requested
         * @private
         */
        _selectPackage: function (packageId, freeTrial) {
            var self = this;
            
            // Find package data
            var pkg = this.packages.find(function (p) { return p.id === packageId; });
            if (!pkg) {
                this._showError('Package not found');
                return;
            }
            
            // Show loading state
            this._showLoading();
            
            // Call server endpoint
            ajax.jsonRpc('/saas/package/select', 'call', {
                package_id: packageId,
                billing_period: this.currentBilling,
                free_trial: freeTrial
            }).then(function (result) {
                self._hideLoading();
                
                if (result.success) {
                    self._showSuccess(result.message);
                    // Future: Redirect to checkout or signup page
                } else {
                    self._showError(result.message || 'Failed to select package');
                }
            }).catch(function (error) {
                self._hideLoading();
                console.error('Error selecting package:', error);
                self._showError('Failed to select package. Please try again.');
            });
        },

        /**
         * Apply dynamic styling based on data attributes
         * @private
         */
        _applyDynamicStyling: function () {
            var $section = this.$el;
            var primaryColor = $section.attr('data-primary-color') || '#875A7B';
            var accentColor = $section.attr('data-accent-color') || '#0066CC';
            var cardBg = $section.attr('data-card-bg') || '#FFFFFF';
            var textColor = $section.attr('data-text-color') || '#333333';
            var borderRadius = $section.attr('data-border-radius') || '8';
            var shadowIntensity = $section.attr('data-shadow-intensity') || '0.1';
            
            // Apply CSS custom properties
            $section.css({
                '--primary-color': primaryColor,
                '--accent-color': accentColor,
                '--card-bg': cardBg,
                '--text-color': textColor,
                '--border-radius': borderRadius + 'px',
                '--shadow-intensity': shadowIntensity
            });
        },

        /**
         * Show error message
         * @param {string} message - Error message
         * @private
         */
        _showError: function (message) {
            var $container = this.$('#pricingCards');
            $container.html('<div class="col-12 text-center"><div class="alert alert-danger">' + message + '</div></div>');
        },

        /**
         * Show success message
         * @param {string} message - Success message
         * @private
         */
        _showSuccess: function (message) {
            var $alert = $('<div class="alert alert-success alert-dismissible fade show" role="alert">')
                .html(message + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>');
            
            this.$('.container').prepend($alert);
            
            // Auto-dismiss after 5 seconds
            setTimeout(function () {
                $alert.alert('close');
            }, 5000);
        },

        /**
         * Show loading state
         * @private
         */
        _showLoading: function () {
            this.$('.btn').prop('disabled', true).append(' <i class="fa fa-spinner fa-spin"></i>');
        },

        /**
         * Hide loading state
         * @private
         */
        _hideLoading: function () {
            this.$('.btn').prop('disabled', false).find('.fa-spinner').remove();
        },
    });

    /**
     * Register widget for automatic initialization
     */
    publicWidget.registry.saaSPricingSnippet = SaaSPricingSnippet;

    return SaaSPricingSnippet;
});

/* ========================================================================== */
/* VANILLA JAVASCRIPT FALLBACK */
/* For cases where Odoo framework is not available */
/* ========================================================================== */

(function() {
    'use strict';
    
    /**
     * Initialize pricing snippet without Odoo framework
     */
    function initPricingSnippet() {
        var sections = document.querySelectorAll('.saas-pricing-section');
        
        sections.forEach(function(section) {
            // Apply dynamic styling
            applyDynamicStyling(section);
            
            // Initialize toggle
            var toggle = section.querySelector('.toggle-input');
            if (toggle) {
                toggle.addEventListener('change', function() {
                    handleBillingToggle(section, this.checked);
                });
            }
            
            // Initialize button clicks
            var buttons = section.querySelectorAll('.btn-main, .btn-trial');
            buttons.forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    handleButtonClick(section, this);
                });
            });
        });
    }
    
    /**
     * Apply dynamic styling to section
     */
    function applyDynamicStyling(section) {
        var primaryColor = section.getAttribute('data-primary-color') || '#875A7B';
        var accentColor = section.getAttribute('data-accent-color') || '#0066CC';
        var cardBg = section.getAttribute('data-card-bg') || '#FFFFFF';
        var textColor = section.getAttribute('data-text-color') || '#333333';
        var borderRadius = section.getAttribute('data-border-radius') || '8';
        var shadowIntensity = section.getAttribute('data-shadow-intensity') || '0.1';
        
        section.style.setProperty('--primary-color', primaryColor);
        section.style.setProperty('--accent-color', accentColor);
        section.style.setProperty('--card-bg', cardBg);
        section.style.setProperty('--text-color', textColor);
        section.style.setProperty('--border-radius', borderRadius + 'px');
        section.style.setProperty('--shadow-intensity', shadowIntensity);
    }
    
    /**
     * Handle billing toggle
     */
    function handleBillingToggle(section, isMonthly) {
        var labels = section.querySelectorAll('.toggle-label');
        labels.forEach(function(label) {
            label.classList.remove('active');
        });
        
        var activeLabel = section.querySelector('.toggle-label[data-period="' + (isMonthly ? 'monthly' : 'yearly') + '"]');
        if (activeLabel) {
            activeLabel.classList.add('active');
        }
    }
    
    /**
     * Handle button clicks
     */
    function handleButtonClick(section, button) {
        var card = button.closest('.saas-pricing-card');
        var packageId = card.getAttribute('data-package-id');
        var isFreeTrial = button.classList.contains('btn-trial');
        
        console.log('Package selected:', packageId, 'Free trial:', isFreeTrial);
        
        // Show feedback
        var originalText = button.textContent;
        button.textContent = 'Processing...';
        button.disabled = true;
        
        setTimeout(function() {
            button.textContent = originalText;
            button.disabled = false;
            alert('Package selection functionality will be implemented soon!');
        }, 1000);
    }
    
    /**
     * Initialize when DOM is ready
     */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPricingSnippet);
    } else {
        initPricingSnippet();
    }
    
})();