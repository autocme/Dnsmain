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
        var isFreeTrial = button.getAttribute('data-is-free-trial') === 'true';
        
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
        
        // Show invoice link for paid packages
        if (!result.is_free_trial && result.invoice_portal_url) {
            var paymentLink = document.getElementById('saasPaymentLink');
            var invoiceLink = document.getElementById('saasInvoiceLink');
            if (paymentLink && invoiceLink) {
                invoiceLink.href = result.invoice_portal_url;
                paymentLink.style.display = 'block';
            }
        }
        
        // Show success screen after a short delay
        setTimeout(function() {
            showSuccessScreen();
        }, 500);
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