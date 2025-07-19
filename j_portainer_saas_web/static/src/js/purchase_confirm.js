/* ========================================================================== */
/* SAAS PURCHASE CONFIRMATION PAGE - JAVASCRIPT */
/* Handles the purchase confirmation flow with elegant loading states */
/* ========================================================================== */

(function() {
    'use strict';
    
    /**
     * Initialize purchase confirmation page when DOM is ready
     */
    function initPurchaseConfirm() {
        console.log('Initializing SaaS purchase confirmation page...');
        
        var startBtn = document.getElementById('saasStartBtn');
        var continueBtn = document.getElementById('saasContinueBtn');
        
        if (startBtn) {
            startBtn.addEventListener('click', handleStartClick);
        }
        
        if (continueBtn) {
            continueBtn.addEventListener('click', handleContinueClick);
        }
    }
    
    /**
     * Handle "Start Now" button click
     */
    function handleStartClick(e) {
        e.preventDefault();
        
        // Find the actual button element (in case click was on child element)
        var button = e.target.closest('.saas_start_btn');
        if (!button) {
            console.error('Could not find button element');
            return;
        }
        
        var packageId = button.getAttribute('data-package-id');
        var billingCycle = button.getAttribute('data-billing-cycle');
        var isFreeTrialAttr = button.getAttribute('data-is-free-trial');
        var isFreeTrial = isFreeTrialAttr === 'true' || isFreeTrialAttr === 'True';
        
        // Debug logging to track the attribute value
        console.log('Button attributes:', {
            'data-package-id': packageId,
            'data-billing-cycle': billingCycle,
            'data-is-free-trial': isFreeTrialAttr,
            'isFreeTrial (converted)': isFreeTrial
        });
        
        console.log('Starting purchase process:', {
            packageId: packageId,
            billingCycle: billingCycle,
            isFreeTrial: isFreeTrial
        });
        
        // Validate required parameters
        if (!packageId || !billingCycle) {
            console.error('Missing required parameters:', {
                packageId: packageId,
                billingCycle: billingCycle
            });
            showErrorMessage('Missing required information. Please refresh the page and try again.');
            return;
        }
        
        // Show loading screen
        showLoadingScreen();
        
        // Disable the button
        button.disabled = true;
        
        // Make purchase request
        makePurchaseRequest(packageId, billingCycle, isFreeTrial);
    }
    
    /**
     * Handle "Continue to Dashboard" button click
     */
    function handleContinueClick(e) {
        e.preventDefault();
        
        // Redirect to client domain if available, otherwise to dashboard
        var redirectUrl = '/web';
        if (window.saasClientResult && window.saasClientResult.client_domain) {
            var clientDomain = window.saasClientResult.client_domain;
            // Check if client_domain is already a clean URL
            if (clientDomain.startsWith('http://') || clientDomain.startsWith('https://')) {
                redirectUrl = clientDomain;
            } else if (clientDomain !== '/web') {
                // Add https if it's a domain without protocol
                redirectUrl = clientDomain.startsWith('http') ? clientDomain : `https://${clientDomain}`;
            }
        }
        
        console.log('Redirecting to:', redirectUrl);
        window.location.href = redirectUrl;
    }
    
    /**
     * Show loading screen with animation
     */
    function showLoadingScreen() {
        var loadingScreen = document.getElementById('saasLoadingScreen');
        if (loadingScreen) {
            loadingScreen.style.display = 'flex';
            
            // Add fade-in animation
            loadingScreen.style.opacity = '0';
            setTimeout(function() {
                loadingScreen.style.opacity = '1';
            }, 10);
        }
    }
    
    /**
     * Hide loading screen
     */
    function hideLoadingScreen() {
        var loadingScreen = document.getElementById('saasLoadingScreen');
        if (loadingScreen) {
            loadingScreen.style.opacity = '0';
            setTimeout(function() {
                loadingScreen.style.display = 'none';
            }, 300);
        }
    }
    
    /**
     * Show success screen with animation
     */
    function showSuccessScreen() {
        var successScreen = document.getElementById('saasSuccessScreen');
        if (successScreen) {
            successScreen.style.display = 'flex';
            
            // Add fade-in animation
            successScreen.style.opacity = '0';
            setTimeout(function() {
                successScreen.style.opacity = '1';
            }, 10);
        }
    }
    
    /**
     * Make purchase request to server
     */
    function makePurchaseRequest(packageId, billingCycle, isFreeTrial) {
        console.log('Making purchase request with:', {
            packageId: packageId,
            billingCycle: billingCycle,
            isFreeTrial: isFreeTrial
        });
        
        // Convert packageId to integer and validate
        var packageIdInt = parseInt(packageId);
        if (isNaN(packageIdInt) || packageIdInt <= 0) {
            console.error('Invalid package ID:', packageId);
            handlePurchaseError('Invalid package ID. Please refresh the page and try again.');
            return;
        }
        
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
                    package_id: packageIdInt,
                    billing_cycle: billingCycle,
                    is_free_trial: isFreeTrial
                }
            })
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            console.log('Purchase response:', data);
            
            // Check for JSON-RPC errors
            if (data.error) {
                handlePurchaseError(data.error.message || 'Purchase failed. Please try again.');
                return;
            }
            
            if (data.result && data.result.success) {
                // Wait a moment for the loading animation, then show success
                setTimeout(function() {
                    handlePurchaseSuccess(data.result);
                }, 2000);
            } else {
                var errorMsg = 'Purchase failed. Please try again.';
                if (data.result && data.result.error) {
                    errorMsg = typeof data.result.error === 'string' ? data.result.error : errorMsg;
                }
                handlePurchaseError(errorMsg);
            }
        })
        .catch(function(error) {
            console.error('Purchase request failed:', error);
            handlePurchaseError('Network error. Please check your connection and try again.');
        });
    }
    
    /**
     * Handle successful purchase
     */
    function handlePurchaseSuccess(result) {
        console.log('Purchase successful:', result);
        
        // Hide loading screen
        hideLoadingScreen();
        
        // Store result data for success screen
        window.saasClientResult = result;
        
        // Handle free trial vs paid packages differently
        if (result.is_free_trial) {
            // For free trial: show success screen as before
            setTimeout(function() {
                showSuccessScreen();
            }, 500);
        } else {
            // For paid packages: hide loading and show payment form (already embedded)
            setTimeout(function() {
                hideLoadingScreen();
                showPaymentForm(result.client_id);
            }, 500);
        }
    }
    
    /**
     * Handle purchase error
     */
    function handlePurchaseError(errorMessage) {
        console.error('Purchase error:', errorMessage);
        
        // Hide loading screen
        hideLoadingScreen();
        
        // Re-enable the start button
        var startBtn = document.getElementById('saasStartBtn');
        if (startBtn) {
            startBtn.disabled = false;
        }
        
        // Show error message
        showErrorMessage(errorMessage);
    }
    
    /**
     * Show payment info for paid packages and setup invoice payment
     */
    function showPaymentForm(clientId) {
        console.log('Showing payment info for client:', clientId);
        
        // Hide package features and show payment info
        var packageFeatures = document.getElementById('saasPackageFeatures');
        var paymentInfo = document.getElementById('saasPaymentInfo');
        
        if (packageFeatures) {
            packageFeatures.style.display = 'none';
        }
        
        if (paymentInfo) {
            paymentInfo.style.display = 'block';
            
            // Update progress step to show payment as current
            updateProgressToPayment();
            
            // Store client ID and setup payment button
            window.saasCurrentClientId = clientId;
            setupInvoicePaymentButton(clientId);
        }
    }
    
    /**
     * Setup the invoice payment button to open Odoo's payment wizard
     */
    function setupInvoicePaymentButton(clientId) {
        var payBtn = document.getElementById('saasPayInvoiceBtn');
        if (payBtn) {
            payBtn.addEventListener('click', function() {
                openInvoicePaymentWizard(clientId);
            });
        }
    }
    
    /**
     * Open Odoo's built-in invoice payment wizard
     */
    function openInvoicePaymentWizard(clientId) {
        console.log('Opening invoice payment wizard for client:', clientId);
        
        // Get the invoice ID for this client via AJAX
        fetch('/saas/client/invoice_info?client_id=' + clientId, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.success && data.invoice_id) {
                // Open Odoo's invoice payment portal
                var invoicePaymentUrl = '/my/invoices/' + data.invoice_id + '?access_token=' + (data.access_token || '');
                
                // Option 1: Open in new window/tab
                var paymentWindow = window.open(invoicePaymentUrl, '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');
                
                // Option 2: If you prefer modal (uncomment this and comment the line above)
                // window.location.href = invoicePaymentUrl;
                
                // Monitor for payment completion (optional)
                if (paymentWindow) {
                    var checkClosed = setInterval(function() {
                        if (paymentWindow.closed) {
                            clearInterval(checkClosed);
                            console.log('Payment window closed, checking payment status...');
                            checkPaymentStatus(clientId);
                        }
                    }, 1000);
                }
            } else {
                console.error('Failed to get invoice info:', data.error || 'Unknown error');
                showErrorMessage('Unable to load payment information. Please try again.');
            }
        })
        .catch(function(error) {
            console.error('Error getting invoice info:', error);
            showErrorMessage('Error loading payment information. Please try again.');
        });
    }
    
    /**
     * Check if payment has been completed
     */
    function checkPaymentStatus(clientId) {
        fetch('/saas/client/payment_status?client_id=' + clientId, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.success && data.paid) {
                console.log('Payment completed, redirecting to instance...');
                // Redirect to the client instance
                if (data.client_url) {
                    window.location.href = data.client_url;
                } else {
                    showSuccessScreen();
                }
            } else {
                console.log('Payment not yet completed');
            }
        })
        .catch(function(error) {
            console.error('Error checking payment status:', error);
        });
    }
    
    /**
     * Load payment wizard for paid packages (DEPRECATED - replaced with embedded form)
     */
    function loadPaymentWizard(clientId) {
        console.log('Loading payment wizard for client:', clientId);
        
        // Hide package features and show loading message
        var packageFeatures = document.getElementById('saasPackageFeatures');
        var paymentWizard = document.getElementById('saasPaymentWizard');
        
        if (packageFeatures) {
            packageFeatures.style.display = 'none';
        }
        
        if (paymentWizard) {
            paymentWizard.style.display = 'block';
            paymentWizard.innerHTML = `
                <div class="text-center" style="padding: 40px;">
                    <div class="saas_spinner" style="margin: 0 auto 20px;"></div>
                    <h5>Loading payment options...</h5>
                </div>
            `;
        }
        
        // Test controller first
        fetch('/saas/test/wizard')
        .then(function(testResp) {
            console.log('Test route status:', testResp.status);
            
            // Fetch payment wizard HTML
            return fetch('/saas/invoice/payment_wizard?client_id=' + clientId, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
        })
        .then(function(response) {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.text();
        })
        .then(function(html) {
            console.log('Payment wizard loaded successfully');
            
            if (paymentWizard) {
                paymentWizard.innerHTML = html;
                
                // Update progress step to show payment as current
                updateProgressToPayment();
            }
        })
        .catch(function(error) {
            console.error('Failed to load payment wizard:', error);
            
            // Show error and fallback to invoice link
            if (paymentWizard) {
                paymentWizard.innerHTML = `
                    <div class="alert alert-danger">
                        <h5>Payment Error</h5>
                        <p>Unable to load payment wizard. Please try again or contact support.</p>
                        <button type="button" class="btn btn-primary" onclick="location.reload();">
                            Retry
                        </button>
                    </div>
                `;
            }
        });
    }
    
    /**
     * Update progress steps to show payment as current
     */
    function updateProgressToPayment() {
        // Update step 2 (payment) to completed
        var step2 = document.querySelector('.saas_steps_progress .saas_step:nth-child(3)');
        if (step2) {
            step2.classList.remove('saas_step_current');
            step2.classList.add('saas_step_completed');
            
            var step2Circle = step2.querySelector('.saas_step_circle');
            if (step2Circle) {
                step2Circle.innerHTML = '<i class="fa fa-check"></i>';
            }
        }
        
        // Update line between step 2 and 3
        var line2 = document.querySelector('.saas_steps_progress .saas_step_line:nth-child(5)');
        if (line2) {
            line2.classList.add('saas_step_line_completed');
        }
        
        // Update step 3 (setup) to current
        var step3 = document.querySelector('.saas_steps_progress .saas_step:nth-child(7)');
        if (step3) {
            step3.classList.add('saas_step_current');
        }
    }
    
    /**
     * Show error message
     */
    function showErrorMessage(message) {
        // Create error alert if it doesn't exist
        var existingAlert = document.querySelector('.saas_error_alert');
        if (existingAlert) {
            existingAlert.remove();
        }
        
        var errorAlert = document.createElement('div');
        errorAlert.className = 'alert alert-danger saas_error_alert';
        errorAlert.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000; max-width: 400px;';
        errorAlert.innerHTML = `
            <button type="button" class="close" onclick="this.parentElement.remove();">
                <span>&times;</span>
            </button>
            <strong>Error:</strong> ${message}
        `;
        
        document.body.appendChild(errorAlert);
        
        // Auto-remove after 5 seconds
        setTimeout(function() {
            if (errorAlert.parentElement) {
                errorAlert.remove();
            }
        }, 5000);
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPurchaseConfirm);
    } else {
        initPurchaseConfirm();
    }
    
})();