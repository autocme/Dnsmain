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
        
        // Check for pending purchase from login redirect
        checkPendingPurchase();
        
        var sections = document.querySelectorAll('.saas-pricing-section');
        
        sections.forEach(function(section) {
            // Apply dynamic styling
            applyDynamicStyling(section);
            
            // Load packages
            loadPackages(section);
            
            // Initialize toggle
            setupBillingToggle(section);
            
            // Initialize button clicks and purchase handlers
            setupButtonClicks(section);
            setupPurchaseHandlers(section);
        });
    }
    
    /**
     * Load packages from server
     */
    function loadPackages(section) {
        var pricingCards = section.querySelector('#pricingCards');
        
        console.log('Loading packages...');
        showLoading(pricingCards);
        
        // Try main endpoint first, fallback to demo, then static
        loadFromEndpoint('/saas/packages/data', pricingCards)
            .then(function(data) {
                console.log('Main endpoint succeeded:', data);
                return data;
            })
            .catch(function(error) {
                console.log('Main endpoint failed, trying demo endpoint...', error);
                return loadFromEndpoint('/saas/packages/demo', pricingCards);
            })
            .then(function(data) {
                if (data) {
                    console.log('Demo endpoint succeeded:', data);
                    return data;
                } else {
                    throw new Error('Demo endpoint returned null');
                }
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
     * Show loading spinner in pricing cards container
     */
    function showLoading(pricingCards) {
        if (pricingCards) {
            pricingCards.innerHTML = `
                <div class="text-center" style="padding: 40px;">
                    <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
                        <span class="sr-only">Loading...</span>
                    </div>
                    <p class="mt-3" style="color: #666;">Loading pricing packages...</p>
                </div>
            `;
        }
    }
    
    /**
     * Show error message in pricing cards container
     */
    function showError(pricingCards, message) {
        if (pricingCards) {
            pricingCards.innerHTML = `
                <div class="text-center" style="padding: 40px;">
                    <div class="alert alert-danger">
                        <h5><i class="fa fa-exclamation-triangle"></i> Error Loading Packages</h5>
                        <p>${message}</p>
                        <button class="btn btn-primary btn-sm" onclick="location.reload();">
                            <i class="fa fa-refresh"></i> Retry
                        </button>
                    </div>
                </div>
            `;
        }
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
        
        // Filter packages based on toggle state
        var filteredPackages = filterPackagesByToggle(packages, section);
        
        filteredPackages.forEach(function(pkg, index) {
            var isHidden = hiddenPackages.includes(pkg.id.toString());
            
            // Get current toggle state to display correct price
            var toggle = section.querySelector('.toggle-input');
            var isMonthly = toggle ? toggle.checked : false;
            var currentPrice = isMonthly ? (pkg.monthly_price || 0) : (pkg.yearly_price || 0);
            var currentPeriod = isMonthly ? '/month' : '/year';
            
            var cardHtml = `
                <div class="pricing-card-col mb-4 ${isHidden ? 'hidden-package' : ''}" data-package-id="${pkg.id}">
                    <div class="saas-pricing-card h-100" data-package-id="${pkg.id}">
                        <div class="card-header">
                            <h3 class="package-name">${pkg.name}</h3>
                            <div class="price-display">
                                <span class="currency-symbol">${pkg.currency_symbol}</span>
                                <span class="price-amount" data-monthly="${pkg.monthly_price || 0}" data-yearly="${pkg.yearly_price || 0}">${currentPrice}</span>
                                <span class="price-period">${currentPeriod}</span>
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
     * Filter packages based on toggle state and activation fields
     */
    function filterPackagesByToggle(packages, section) {
        // Get toggle state - checked = monthly, unchecked = yearly
        var toggle = section.querySelector('.toggle-input');
        var isMonthly = toggle ? toggle.checked : false;
        
        return packages.filter(function(pkg) {
            if (isMonthly) {
                // Show packages that have monthly active
                return pkg.monthly_active;
            } else {
                // Show packages that have yearly active
                return pkg.yearly_active;
            }
        });
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
     * Setup purchase handlers for all buttons
     */
    function setupPurchaseHandlers(section) {
        // Use event delegation to handle dynamically created buttons
        section.addEventListener('click', function(e) {
            var target = e.target;
            
            // Check if clicked element is a purchase button or inside one
            var button = target.closest('.btn-main, .btn-trial');
            
            if (button) {
                e.preventDefault();
                console.log('Button clicked:', {
                    type: button.classList.contains('btn-trial') ? 'Free Trial' : 'Buy Now',
                    classes: button.className,
                    target: target,
                    button: button
                });
                handlePurchaseClick(button, section);
            } else {
                console.log('Click not on button:', target);
            }
        });
    }
    
    /**
     * Handle purchase button clicks
     */
    function handlePurchaseClick(button, section) {
        console.log('handlePurchaseClick called with button:', button);
        
        // Get package information
        var card = button.closest('.saas-pricing-card');
        if (!card) {
            console.error('No saas-pricing-card found for button:', button);
            return;
        }
        
        var packageId = card.getAttribute('data-package-id');
        var isFreeTrial = button.classList.contains('btn-trial');
        
        console.log('Purchase details:', {
            packageId: packageId,
            isFreeTrial: isFreeTrial,
            buttonClasses: button.className
        });
        
        // Get current billing cycle
        var toggle = section.querySelector('.toggle-input');
        var billingCycle = (toggle && toggle.checked) ? 'monthly' : 'yearly';
        
        // Debug billing cycle selection
        console.log('Purchase Request - Toggle checked:', toggle ? toggle.checked : 'null', 'Billing cycle:', billingCycle);
        
        if (!packageId) {
            console.error('Package ID not found on card:', card);
            showError('Package information not found');
            return;
        }
        
        // Show loading state
        showLoadingState(button);
        
        // Redirect to confirmation page instead of direct purchase
        var confirmUrl = `/saas/purchase/confirm?package_id=${packageId}&billing_cycle=${billingCycle}&is_free_trial=${isFreeTrial}`;
        window.location.href = confirmUrl;
    }
    
    /**
     * Make purchase request to server
     */
    function makePurchaseRequest(packageId, billingCycle, isFreeTrial, button) {
        console.log('makePurchaseRequest called with:', {
            packageId: packageId,
            billingCycle: billingCycle,
            isFreeTrial: isFreeTrial,
            button: button
        });
        
        fetch('/saas/package/purchase', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: {
                    package_id: parseInt(packageId),
                    billing_cycle: billingCycle,
                    is_free_trial: isFreeTrial
                }
            })
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            // Check for authentication errors (Odoo returns error code 100 for authentication failures)
            if (data.error && (data.error.code === 100 || data.error.message.includes('authentication') || data.error.message.includes('login'))) {
                hideLoadingState(button);
                
                // Store purchase details to resume after login
                sessionStorage.setItem('pendingPurchase', JSON.stringify({
                    packageId: packageId,
                    billingCycle: billingCycle,
                    isFreeTrial: isFreeTrial
                }));
                
                // Redirect to login page immediately
                window.location.href = '/web/login';
                return;
            }
            
            // Check for other JSON-RPC errors
            if (data.error) {
                hideLoadingState(button);
                var errorMessage = data.error.message || 'Purchase failed. Please try again.';
                try {
                    showError(errorMessage);
                } catch (e) {
                    console.error('Error showing error message:', e);
                }
                return;
            }
            
            hideLoadingState(button);
            
            if (data.result && data.result.success) {
                handlePurchaseSuccess(data.result);
            } else if (data.result && data.result.redirect_login) {
                handleLoginRequired();
            } else {
                var errorMsg = 'Purchase failed. Please try again.';
                if (data.result && data.result.error) {
                    errorMsg = typeof data.result.error === 'string' ? data.result.error : 'Purchase failed. Please try again.';
                }
                try {
                    showError(errorMsg);
                } catch (e) {
                    console.error('Error showing error message:', e);
                }
            }
        })
        .catch(function(error) {
            hideLoadingState(button);
            console.error('Purchase request failed:', error);
            
            // Check if it's a network error that might indicate authentication issues
            if (error.message && (error.message.includes('401') || error.message.includes('403'))) {
                // Store purchase details to resume after login
                sessionStorage.setItem('pendingPurchase', JSON.stringify({
                    packageId: packageId,
                    billingCycle: billingCycle,
                    isFreeTrial: isFreeTrial
                }));
                
                // Redirect to login page immediately
                window.location.href = '/web/login';
                return;
            }
            
            // Ensure we pass a string to showError
            var errorMessage = 'Network error. Please check your connection and try again.';
            if (error && typeof error === 'object' && error.message) {
                errorMessage = error.message;
            } else if (typeof error === 'string') {
                errorMessage = error;
            }
            
            try {
                showError(errorMessage);
            } catch (e) {
                console.error('Error showing error message:', e);
            }
        });
    }
    
    /**
     * Check for pending purchase after login redirect
     */
    function checkPendingPurchase() {
        var pendingPurchase = sessionStorage.getItem('pendingPurchase');
        if (pendingPurchase) {
            try {
                var purchaseData = JSON.parse(pendingPurchase);
                console.log('Found pending purchase after login, resuming...', purchaseData);
                
                // Clear the pending purchase
                sessionStorage.removeItem('pendingPurchase');
                
                // Wait for DOM to be ready and then complete the purchase
                setTimeout(function() {
                    completePendingPurchase(purchaseData);
                }, 1000);
                
            } catch (e) {
                console.error('Error parsing pending purchase data:', e);
                sessionStorage.removeItem('pendingPurchase');
            }
        }
    }
    
    /**
     * Complete pending purchase after login
     */
    function completePendingPurchase(purchaseData) {
        console.log('Completing pending purchase...', purchaseData);
        
        // Create a temporary button for loading state management
        var tempButton = document.createElement('button');
        tempButton.textContent = 'Processing...';
        tempButton.disabled = true;
        
        // Make the purchase request
        makePurchaseRequest(purchaseData.packageId, purchaseData.billingCycle, purchaseData.isFreeTrial, tempButton);
    }
    
    /**
     * Handle successful purchase
     */
    function handlePurchaseSuccess(result) {
        // Redirect immediately without showing success message
        window.location.href = result.redirect_url;
    }
    
    /**
     * Handle login required scenario
     */
    function handleLoginRequired() {
        showError('Please log in to purchase a package');
        
        // Redirect to login page after delay
        setTimeout(function() {
            window.location.href = '/web/login';
        }, 2000);
    }
    
    /**
     * Show loading state on button
     */
    function showLoadingState(button) {
        if (button._originalHTML) return; // Already in loading state
        
        button._originalHTML = button.innerHTML;
        button.innerHTML = '<span class="btn-text">Processing...</span><i class="fa fa-spinner fa-spin btn-icon"></i>';
        button.disabled = true;
        button.style.opacity = '0.7';
    }
    
    /**
     * Hide loading state on button
     */
    function hideLoadingState(button) {
        if (button._originalHTML) {
            button.innerHTML = button._originalHTML;
            delete button._originalHTML;
        }
        button.disabled = false;
        button.style.opacity = '1';
    }
    
    /**
     * Show success message
     */
    function showSuccess(message) {
        showMessage(message, 'success');
    }
    
    /**
     * Show error message
     */
    function showError(message) {
        showMessage(message, 'error');
    }
    
    /**
     * Show message to user
     */
    function showMessage(message, type) {
        // Ensure message is a string
        if (typeof message !== 'string') {
            message = String(message);
        }
        
        // Remove existing messages
        var existingMessages = document.querySelectorAll('.saas-purchase-message');
        existingMessages.forEach(function(msg) {
            msg.remove();
        });
        
        // Create message element
        var messageDiv = document.createElement('div');
        messageDiv.className = 'saas-purchase-message alert alert-' + (type === 'success' ? 'success' : 'danger');
        messageDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999; max-width: 400px; padding: 15px; border-radius: 5px;';
        
        // Create message content
        var messageContent = document.createElement('span');
        messageContent.textContent = message;
        messageDiv.appendChild(messageContent);
        
        // Create close button
        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close';
        closeBtn.style.cssText = 'float: right; margin-left: 10px; background: none; border: none; font-size: 18px; cursor: pointer;';
        closeBtn.innerHTML = '&times;';
        closeBtn.addEventListener('click', function() {
            messageDiv.remove();
        });
        messageDiv.appendChild(closeBtn);
        
        // Add to page
        document.body.appendChild(messageDiv);
        
        // Auto-remove after 5 seconds
        setTimeout(function() {
            if (messageDiv.parentNode) {
                messageDiv.remove();
            }
        }, 5000);
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
        
        // Re-render packages with new filter
        if (window.allPackages) {
            var pricingCards = section.querySelector('#pricingCards');
            renderPackages(pricingCards, window.allPackages);
        }
        
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
        // This function is now handled by setupPurchaseHandlers
        // Remove old alert functionality as purchase logic is implemented
        console.log('Button click delegated to purchase handler');
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