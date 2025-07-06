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
        
        // Try main endpoint first, fallback to demo, then static
        loadFromEndpoint('/saas/packages/data', pricingCards)
            .catch(function(error) {
                console.log('Main endpoint failed, trying demo endpoint...', error);
                return loadFromEndpoint('/saas/packages/demo', pricingCards);
            })
            .catch(function(error) {
                console.log('Demo endpoint failed, using static fallback...', error);
                return loadStaticPackages(pricingCards);
            })
            .catch(function(error) {
                console.error('All loading methods failed:', error);
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
                console.log('Successfully loaded ' + (data.packages ? data.packages.length : 0) + ' packages from ' + endpoint);
                renderPackages(pricingCards, data.packages || []);
                return data;
            } else if (data && data.error) {
                console.log('Server error from ' + endpoint + ':', data.error);
                if (data.debug) {
                    console.log('Debug info:', data.debug);
                }
                throw new Error('Server error: ' + data.error);
            } else {
                console.log('Unexpected response format from ' + endpoint + ':', data);
                throw new Error('No packages found or server error');
            }
        });
    }
    
    /**
     * Load static packages as final fallback
     */
    function loadStaticPackages(pricingCards) {
        console.log('Loading static fallback packages...');
        
        var staticPackages = [
            {
                'id': 1,
                'name': 'Starter',
                'description': 'Perfect for small teams getting started',
                'monthly_price': 29.0,
                'yearly_price': 261.0,
                'currency_symbol': '$',
                'has_free_trial': true,
                'subscription_period': 'monthly',
                'features': [
                    '5 Projects',
                    '10GB Storage',
                    'Email Support',
                    'Basic Analytics'
                ]
            },
            {
                'id': 2,
                'name': 'Professional',
                'description': 'For growing businesses with advanced needs',
                'monthly_price': 79.0,
                'yearly_price': 711.0,
                'currency_symbol': '$',
                'has_free_trial': true,
                'subscription_period': 'monthly',
                'features': [
                    '25 Projects',
                    '100GB Storage',
                    'Priority Support',
                    'Advanced Analytics'
                ]
            },
            {
                'id': 3,
                'name': 'Enterprise',
                'description': 'For large organizations with complex requirements',
                'monthly_price': 199.0,
                'yearly_price': 1791.0,
                'currency_symbol': '$',
                'has_free_trial': false,
                'subscription_period': 'monthly',
                'features': [
                    'Unlimited Projects',
                    '1TB Storage',
                    'Dedicated Support',
                    'Custom Analytics'
                ]
            }
        ];
        
        return new Promise(function(resolve) {
            setTimeout(function() {
                renderPackages(pricingCards, staticPackages);
                resolve({ success: true, packages: staticPackages });
            }, 100);
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
        
        // Store packages globally for visibility controls
        window.allPackages = packages;
        
        // Get section to check for layout preferences
        var section = container.closest('.saas-pricing-section');
        var hiddenPackages = getHiddenPackages(section);
        
        packages.forEach(function(pkg, index) {
            var isHidden = hiddenPackages.includes(pkg.id.toString());
            var cardHtml = `
                <div class="pricing-card-col mb-4 ${isHidden ? 'hidden-package' : ''}" data-package-id="${pkg.id}">
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
                        
                        <!-- Package visibility control for editors -->
                        <div class="package-editor-controls" style="display: none;">
                            <button class="btn btn-sm btn-danger hide-package-btn" onclick="togglePackageVisibility(${pkg.id})">
                                <i class="fa fa-eye-slash"></i> Hide Package
                            </button>
                        </div>
                    </div>
                </div>
            `;
            container.innerHTML += cardHtml;
        });
        
        // Apply column layout
        updateColumnLayout(section);
        
        // Populate package controls in snippet options if available
        setTimeout(function() {
            populatePackageCheckboxes(packages);
        }, 100);
        
        console.log('Rendered', packages.length, 'packages');
    }
    
    /**
     * Get hidden packages from section data
     */
    function getHiddenPackages(section) {
        var hiddenPackagesAttr = section.getAttribute('data-hidden-packages');
        return hiddenPackagesAttr ? hiddenPackagesAttr.split(',') : [];
    }
    
    /**
     * Update column layout based on section settings
     */
    function updateColumnLayout(section) {
        var columnsPerRow = section.getAttribute('ColumnsPerRow') || '3';
        section.setAttribute('ColumnsPerRow', columnsPerRow);
        
        // Update CSS classes on all pricing card columns
        var cardCols = section.querySelectorAll('.pricing-card-col');
        cardCols.forEach(function(col) {
            // Remove old Bootstrap classes
            col.classList.remove('col-lg-4', 'col-lg-6', 'col-md-6', 'col-sm-12');
            
            // Add new classes based on layout preference
            if (columnsPerRow === '2') {
                col.classList.add('col-lg-6', 'col-md-6', 'col-sm-12');
            } else {
                col.classList.add('col-lg-4', 'col-md-6', 'col-sm-12');
            }
        });
    }
    
    /**
     * Toggle package visibility
     */
    function togglePackageVisibility(packageId) {
        var section = document.querySelector('.saas-pricing-section');
        var hiddenPackages = getHiddenPackages(section);
        var packageIdStr = packageId.toString();
        
        if (hiddenPackages.includes(packageIdStr)) {
            // Show package
            hiddenPackages = hiddenPackages.filter(function(id) { return id !== packageIdStr; });
        } else {
            // Hide package
            hiddenPackages.push(packageIdStr);
        }
        
        // Update section attribute
        section.setAttribute('data-hidden-packages', hiddenPackages.join(','));
        
        // Update display
        var packageCol = section.querySelector('.pricing-card-col[data-package-id="' + packageId + '"]');
        if (packageCol) {
            if (hiddenPackages.includes(packageIdStr)) {
                packageCol.classList.add('hidden-package');
            } else {
                packageCol.classList.remove('hidden-package');
            }
        }
        
        console.log('Toggled visibility for package', packageId, 'Hidden packages:', hiddenPackages);
    }
    
    /**
     * Show package editor controls (for website builder mode)
     */
    function showPackageEditorControls() {
        var controls = document.querySelectorAll('.package-editor-controls');
        controls.forEach(function(control) {
            control.style.display = 'block';
        });
    }
    
    /**
     * Hide package editor controls
     */
    function hidePackageEditorControls() {
        var controls = document.querySelectorAll('.package-editor-controls');
        controls.forEach(function(control) {
            control.style.display = 'none';
        });
    }
    
    /**
     * Refresh package controls in snippet options
     */
    function refreshPackageControls() {
        if (window.allPackages && window.allPackages.length > 0) {
            populatePackageCheckboxes(window.allPackages);
        } else {
            console.log('No packages available to refresh controls');
        }
    }
    
    /**
     * Populate package checkboxes in snippet options
     */
    function populatePackageCheckboxes(packages) {
        var checkboxContainer = document.getElementById('packageCheckboxes');
        if (!checkboxContainer) return;
        
        var section = document.querySelector('.saas-pricing-section');
        var hiddenPackages = getHiddenPackages(section);
        
        checkboxContainer.innerHTML = '';
        
        packages.forEach(function(pkg) {
            var isVisible = !hiddenPackages.includes(pkg.id.toString());
            var checkboxHtml = `
                <div class="form-check mb-1">
                    <input class="form-check-input" type="checkbox" 
                           id="package_${pkg.id}" 
                           ${isVisible ? 'checked' : ''}
                           onchange="handlePackageCheckboxChange(${pkg.id}, this.checked)">
                    <label class="form-check-label small" for="package_${pkg.id}">
                        ${pkg.name}
                    </label>
                </div>
            `;
            checkboxContainer.innerHTML += checkboxHtml;
        });
    }
    
    /**
     * Handle package checkbox changes
     */
    function handlePackageCheckboxChange(packageId, isChecked) {
        if (isChecked) {
            // Show package
            showPackage(packageId);
        } else {
            // Hide package
            hidePackage(packageId);
        }
    }
    
    /**
     * Show a specific package
     */
    function showPackage(packageId) {
        var section = document.querySelector('.saas-pricing-section');
        var hiddenPackages = getHiddenPackages(section);
        var packageIdStr = packageId.toString();
        
        hiddenPackages = hiddenPackages.filter(function(id) { return id !== packageIdStr; });
        section.setAttribute('data-hidden-packages', hiddenPackages.join(','));
        
        var packageCol = section.querySelector('.pricing-card-col[data-package-id="' + packageId + '"]');
        if (packageCol) {
            packageCol.classList.remove('hidden-package');
        }
    }
    
    /**
     * Hide a specific package
     */
    function hidePackage(packageId) {
        var section = document.querySelector('.saas-pricing-section');
        var hiddenPackages = getHiddenPackages(section);
        var packageIdStr = packageId.toString();
        
        if (!hiddenPackages.includes(packageIdStr)) {
            hiddenPackages.push(packageIdStr);
        }
        section.setAttribute('data-hidden-packages', hiddenPackages.join(','));
        
        var packageCol = section.querySelector('.pricing-card-col[data-package-id="' + packageId + '"]');
        if (packageCol) {
            packageCol.classList.add('hidden-package');
        }
    }
    
    // Make functions globally available for editor controls
    window.togglePackageVisibility = togglePackageVisibility;
    window.showPackageEditorControls = showPackageEditorControls;
    window.hidePackageEditorControls = hidePackageEditorControls;
    window.refreshPackageControls = refreshPackageControls;
    window.handlePackageCheckboxChange = handlePackageCheckboxChange;
    
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
        
        // Apply column layout if already rendered
        updateColumnLayout(section);
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