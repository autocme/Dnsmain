/* ========================================================================== */
/* SAAS PRICING SNIPPET OPTIONS JAVASCRIPT */
/* Website editor options for dynamic styling */
/* ========================================================================== */

odoo.define('j_portainer_saas_web.snippet_options', function (require) {
    'use strict';
    
    var options = require('web_editor.snippets.options');
    
    /**
     * SaaS Pricing Snippet Options
     * Handles dynamic styling and customization options
     */
    var SaaSPricingOptions = options.Class.extend({
        
        /**
         * Handle color scheme selection
         */
        selectColorScheme: function (previewMode, value, $opt) {
            var $section = this.$target;
            var scheme = $opt.data('selectDataAttribute');
            var primaryColor = $opt.data('primaryColor');
            var accentColor = $opt.data('accentColor');
            
            if (scheme === 'custom') {
                // Keep current colors for custom
                return;
            }
            
            // Apply predefined color scheme
            $section.attr('data-primary-color', primaryColor);
            $section.attr('data-accent-color', accentColor);
            
            this._applyDynamicStyling();
        },
        
        /**
         * Handle primary color change
         */
        setPrimaryColor: function (previewMode, value, $opt) {
            this.$target.attr('data-primary-color', value);
            this._applyDynamicStyling();
        },
        
        /**
         * Handle accent color change
         */
        setAccentColor: function (previewMode, value, $opt) {
            this.$target.attr('data-accent-color', value);
            this._applyDynamicStyling();
        },
        
        /**
         * Handle card background change
         */
        setCardBg: function (previewMode, value, $opt) {
            this.$target.attr('data-card-bg', value);
            this._applyDynamicStyling();
        },
        
        /**
         * Handle text color change
         */
        setTextColor: function (previewMode, value, $opt) {
            this.$target.attr('data-text-color', value);
            this._applyDynamicStyling();
        },
        
        /**
         * Handle border radius change
         */
        setBorderRadius: function (previewMode, value, $opt) {
            this.$target.attr('data-border-radius', value);
            this._applyDynamicStyling();
        },
        
        /**
         * Handle shadow intensity change
         */
        setShadowIntensity: function (previewMode, value, $opt) {
            this.$target.attr('data-shadow-intensity', value);
            this._applyDynamicStyling();
        },
        
        /**
         * Handle card layout change
         */
        setCardLayout: function (previewMode, value, $opt) {
            var $section = this.$target;
            var layout = $opt.data('selectDataAttribute');
            
            // Remove existing layout classes
            $section.removeClass('layout-default layout-compact layout-spacious');
            
            // Add new layout class
            $section.addClass('layout-' + layout);
        },
        
        /**
         * Handle button style change
         */
        setButtonStyle: function (previewMode, value, $opt) {
            var $section = this.$target;
            var style = $opt.data('selectDataAttribute');
            
            // Remove existing button style classes
            $section.removeClass('btn-style-default btn-style-rounded btn-style-sharp btn-style-pill');
            
            // Add new button style class
            $section.addClass('btn-style-' + style);
        },
        
        /**
         * Handle hover effects change
         */
        setHoverEffects: function (previewMode, value, $opt) {
            var $section = this.$target;
            var effect = $opt.data('selectDataAttribute');
            
            // Remove existing hover effect classes
            $section.removeClass('hover-default hover-lift hover-scale hover-glow hover-none');
            
            // Add new hover effect class
            $section.addClass('hover-' + effect);
        },
        
        /**
         * Reset to default styling
         */
        resetToDefault: function (previewMode, value, $opt) {
            var $section = this.$target;
            
            // Reset all data attributes to defaults
            $section.attr('data-primary-color', '#875A7B');
            $section.attr('data-accent-color', '#0066CC');
            $section.attr('data-card-bg', '#FFFFFF');
            $section.attr('data-text-color', '#333333');
            $section.attr('data-border-radius', '8');
            $section.attr('data-shadow-intensity', '0.1');
            
            // Remove all modifier classes
            $section.removeClass(function (index, className) {
                return (className.match(/(^|\s)layout-\S+/g) || []).join(' ');
            });
            $section.removeClass(function (index, className) {
                return (className.match(/(^|\s)btn-style-\S+/g) || []).join(' ');
            });
            $section.removeClass(function (index, className) {
                return (className.match(/(^|\s)hover-\S+/g) || []).join(' ');
            });
            
            // Apply default styling
            this._applyDynamicStyling();
        },
        
        /**
         * Apply dynamic styling based on attributes
         */
        _applyDynamicStyling: function () {
            var $section = this.$target;
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
        }
    });
    
    /**
     * Register the options class
     */
    options.registry.SaaSPricingOptions = SaaSPricingOptions;
    
    return SaaSPricingOptions;
});