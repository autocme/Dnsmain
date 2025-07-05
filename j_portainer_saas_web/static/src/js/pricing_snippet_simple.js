/* ========================================================================== */
/* SAAS PRICING SNIPPET - VANILLA JAVASCRIPT */
/* Simple implementation without Odoo dependencies */
/* ========================================================================== */

(function() {
    'use strict';
    
    /**
     * Initialize pricing snippet when DOM is ready
     */
    function initPricingSnippet() {
        console.log('Initializing SaaS pricing snippet...');
        
        var sections = document.querySelectorAll('.saas-pricing-section');
        
        sections.forEach(function(section) {
            // Apply dynamic styling
            applyDynamicStyling(section);
            
            // Load packages
            loadPackages(section);
            
            // Initialize toggle
            setupBillingToggle(section);
            
            // Initialize button clicks
            setupButtonClicks(section);
        });
    }
    
    /**
     * Load packages from server
     */
    function loadPackages(section) {
        var pricingCards = section.querySelector('#pricingCards');
        
        console.log('Loading packages...');
        
        // Try main endpoint first, fallback to demo
        loadFromEndpoint('/saas/packages/data', pricingCards)
            .catch(function(error) {
                console.log('Main endpoint failed, trying demo endpoint...', error);
                return loadFromEndpoint('/saas/packages/demo', pricingCards);
            })
            .catch(function(error) {
                console.error('Both endpoints failed:', error);
                showError(pricingCards, 'Failed to load packages. Please check your connection.');
            });
    }
    
    /**
     * Load packages from a specific endpoint
     */
    function loadFromEndpoint(endpoint, pricingCards) {
        return fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({})
        })
        .then(function(response) {
            console.log('Response from ' + endpoint + ':', response);
            if (!response.ok) {
                throw new Error('HTTP error! status: ' + response.status);
            }
            return response.json();
        })
        .then(function(data) {
            console.log('Server response from ' + endpoint + ':', data);
            
            // Handle direct response format
            if (data && data.success) {
                renderPackages(pricingCards, data.packages || []);
                return data;
            } else if (data && data.error) {
                throw new Error('Server error: ' + data.error);
            } else {
                throw new Error('No packages found or server error');
            }
        });
    }
    
    /**
     * Render packages in the pricing cards container
     */
    function renderPackages(container, packages) {
        container.innerHTML = '';
        
        if (packages.length === 0) {
            container.innerHTML = '<div class="col-12 text-center"><p>No packages available at the moment.</p></div>';
            return;
        }
        
        packages.forEach(function(pkg) {
            var cardHtml = `
                <div class="col-lg-4 col-md-6 mb-4">
                    <div class="saas-pricing-card h-100" data-package-id="${pkg.id}">
                        <div class="card-header">
                            <h3 class="package-name">${pkg.name}</h3>
                            <div class="price-display">
                                <span class="currency-symbol">${pkg.currency_symbol}</span>
                                <span class="price-amount" data-monthly="${pkg.monthly_price}" data-yearly="${pkg.yearly_price}">${pkg.monthly_price}</span>
                                <span class="price-period">/month</span>
                            </div>
                        </div>
                        <div class="card-body">
                            <div class="package-description">${pkg.description}</div>
                            <ul class="features-list">
                                ${pkg.features.map(feature => `<li>${feature}</li>`).join('')}
                            </ul>
                        </div>
                        <div class="card-footer">
                            <button class="btn btn-primary btn-main" data-action="buy">
                                <span class="btn-text">Buy Now</span>
                                <i class="fa fa-arrow-right btn-icon"></i>
                            </button>
                            ${pkg.has_free_trial ? `
                                <button class="btn btn-outline-secondary btn-trial" data-action="trial">
                                    <span class="btn-text">Free Trial</span>
                                    <i class="fa fa-gift btn-icon"></i>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
            container.innerHTML += cardHtml;
        });
        
        console.log('Rendered', packages.length, 'packages');
    }
    
    /**
     * Setup billing toggle functionality
     */
    function setupBillingToggle(section) {
        var toggle = section.querySelector('.toggle-input');
        if (toggle) {
            toggle.addEventListener('change', function() {
                var isMonthly = this.checked;
                updateBillingDisplay(section, isMonthly);
            });
        }
    }
    
    /**
     * Update billing display when toggle changes
     */
    function updateBillingDisplay(section, isMonthly) {
        var labels = section.querySelectorAll('.toggle-label');
        var priceAmounts = section.querySelectorAll('.price-amount');
        var pricePeriods = section.querySelectorAll('.price-period');
        
        // Update labels
        labels.forEach(function(label) {
            label.classList.remove('active');
        });
        
        var activeLabel = section.querySelector('.toggle-label[data-period="' + (isMonthly ? 'monthly' : 'yearly') + '"]');
        if (activeLabel) {
            activeLabel.classList.add('active');
        }
        
        // Update prices and periods
        priceAmounts.forEach(function(priceEl) {
            var monthlyPrice = parseFloat(priceEl.getAttribute('data-monthly'));
            var yearlyPrice = parseFloat(priceEl.getAttribute('data-yearly'));
            priceEl.textContent = isMonthly ? monthlyPrice : yearlyPrice;
        });
        
        pricePeriods.forEach(function(periodEl) {
            periodEl.textContent = isMonthly ? '/month' : '/year';
        });
    }
    
    /**
     * Setup button click handlers
     */
    function setupButtonClicks(section) {
        // Use event delegation for dynamically added buttons
        section.addEventListener('click', function(e) {
            var button = e.target.closest('.btn-main, .btn-trial');
            if (button) {
                e.preventDefault();
                handleButtonClick(button);
            }
        });
    }
    
    /**
     * Handle button clicks
     */
    function handleButtonClick(button) {
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
     * Show error message
     */
    function showError(container, message) {
        container.innerHTML = `
            <div class="col-12 text-center">
                <div class="alert alert-warning" role="alert">
                    <i class="fa fa-exclamation-triangle"></i>
                    ${message}
                </div>
            </div>
        `;
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