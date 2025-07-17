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
        var payBtn = document.getElementById('saasPayBtn');
        var continueBtn = document.getElementById('saasContinueBtn');
        
        if (startBtn) {
            startBtn.addEventListener('click', handleStartClick);
        }
        
        if (payBtn) {
            payBtn.addEventListener('click', handlePayClick);
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
     * Handle "Pay Now" button click
     */
    function handlePayClick(e) {
        e.preventDefault();
        
        // Find the actual button element
        var button = e.target.closest('.saas_pay_btn');
        if (!button) {
            console.error('Could not find pay button element');
            return;
        }
        
        // Check if payment form exists (fallback to regular purchase if not)
        var paymentForm = document.getElementById('saasPaymentForm');
        if (!paymentForm) {
            console.log('Payment form not found, falling back to regular purchase flow');
            // Fallback to regular purchase request
            makePurchaseRequest(packageId, billingCycle, false);
            return;
        }
        
        var selectedAcquirer = paymentForm.querySelector('input[name="acquirer_id"]:checked');
        if (!selectedAcquirer) {
            showErrorMessage('Please select a payment method to continue.');
            return;
        }
        
        var packageId = button.getAttribute('data-package-id');
        var billingCycle = button.getAttribute('data-billing-cycle');
        
        console.log('Starting payment process:', {
            packageId: packageId,
            billingCycle: billingCycle,
            acquirerId: selectedAcquirer.value
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
        
        // Process payment
        processPayment(packageId, billingCycle, selectedAcquirer.value);
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
     * Process payment through Odoo payment acquirer
     */
    function processPayment(packageId, billingCycle, acquirerId) {
        console.log('Processing payment...', {
            packageId: packageId,
            billingCycle: billingCycle,
            acquirerId: acquirerId
        });
        
        // Submit payment form to Odoo payment processing
        var paymentForm = document.getElementById('saasPaymentForm');
        if (paymentForm) {
            // Add acquirer_id to form if not already present
            var acquirerInput = paymentForm.querySelector('input[name="acquirer_id"]:checked');
            if (acquirerInput) {
                paymentForm.submit();
            } else {
                console.error('No payment method selected');
                showErrorMessage('Please select a payment method.');
                hideLoadingScreen();
                var payBtn = document.getElementById('saasPayBtn');
                if (payBtn) payBtn.disabled = false;
            }
        } else {
            console.error('Payment form not found');
            showErrorMessage('Payment form not found. Please refresh the page.');
            hideLoadingScreen();
            var payBtn = document.getElementById('saasPayBtn');
            if (payBtn) payBtn.disabled = false;
        }
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
    
    /**
     * Handle checkout button click (redirect to ecommerce-style checkout)
     */
    function handleCheckoutClick() {
        var checkoutBtn = document.getElementById('saasCheckoutBtn');
        if (!checkoutBtn) {
            console.error('Checkout button not found');
            return;
        }
        
        // Get package data from button attributes
        var packageId = checkoutBtn.getAttribute('data-package-id');
        var billingCycle = checkoutBtn.getAttribute('data-billing-cycle');
        var price = checkoutBtn.getAttribute('data-price');
        var currencySymbol = checkoutBtn.getAttribute('data-currency-symbol');
        var periodText = checkoutBtn.getAttribute('data-period-text');
        
        console.log('Checkout button clicked:', {
            packageId: packageId,
            billingCycle: billingCycle,
            price: price,
            currencySymbol: currencySymbol,
            periodText: periodText
        });
        
        // For now, redirect to regular purchase flow
        // In a full ecommerce implementation, this would go to a proper checkout page
        makePurchaseRequest(packageId, billingCycle, false);
    }
    
    /**
     * Handle pay now button click (ecommerce-style payment)
     */
    function handlePayNowClick() {
        var payNowBtn = document.getElementById('saasPayNowBtn');
        if (!payNowBtn) {
            console.error('Pay now button not found');
            return;
        }
        
        // Disable button to prevent double clicks
        payNowBtn.disabled = true;
        
        // Get package data from button attributes
        var packageId = payNowBtn.getAttribute('data-package-id');
        var billingCycle = payNowBtn.getAttribute('data-billing-cycle');
        var isFreeTrial = payNowBtn.getAttribute('data-is-free-trial');
        
        console.log('Pay now button clicked:', {
            packageId: packageId,
            billingCycle: billingCycle,
            isFreeTrial: isFreeTrial
        });
        
        // Show loading screen
        showLoadingScreen();
        
        // Make purchase request
        makePurchaseRequest(packageId, billingCycle, false);
    }
    
    /**
     * Initialize purchase confirmation page
     */
    function initPurchaseConfirm() {
        // Start button for free trials
        var startBtn = document.getElementById('saasStartBtn');
        if (startBtn) {
            startBtn.addEventListener('click', handleStartClick);
        }
        
        // Pay button for paid packages (legacy)
        var payBtn = document.getElementById('saasPayBtn');
        if (payBtn) {
            payBtn.addEventListener('click', handlePayClick);
        }
        
        // New checkout button for paid packages
        var checkoutBtn = document.getElementById('saasCheckoutBtn');
        if (checkoutBtn) {
            checkoutBtn.addEventListener('click', handleCheckoutClick);
        }
        
        // Pay now button for paid packages (ecommerce style)
        var payNowBtn = document.getElementById('saasPayNowBtn');
        if (payNowBtn) {
            payNowBtn.addEventListener('click', handlePayNowClick);
        }
        
        // Continue button (success screen)
        var continueBtn = document.getElementById('saasContinueBtn');
        if (continueBtn) {
            continueBtn.addEventListener('click', handleContinueClick);
        }
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPurchaseConfirm);
    } else {
        initPurchaseConfirm();
    }
    
})();