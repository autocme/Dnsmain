/**
 * SaaS Payment Completion Redirect Handler
 * 
 * This script monitors for payment completion and automatically redirects
 * users to their SaaS instance subdomain after successful payment.
 */

(function() {
    'use strict';
    
    console.log('SaaS Payment Redirect Handler initialized');
    
    /**
     * Check if payment was completed and redirect to client subdomain
     */
    function checkPaymentCompletion() {
        // Only run on payment success pages
        if (!window.location.href.includes('/payment/') && 
            !window.location.href.includes('/invoice/') &&
            !document.querySelector('.alert-success')) {
            return;
        }
        
        console.log('Checking for SaaS payment completion...');
        
        // Check for payment completion indicators
        var paymentSuccess = (
            document.querySelector('.alert-success') ||
            document.querySelector('[class*="success"]') ||
            window.location.href.includes('payment_status=done') ||
            document.body.innerHTML.includes('Thank you') ||
            document.body.innerHTML.includes('successfully processed')
        );
        
        if (paymentSuccess) {
            console.log('Payment success detected, checking for SaaS client...');
            checkForSaasClient();
        }
    }
    
    /**
     * Check for SaaS client redirect information
     */
    function checkForSaasClient() {
        fetch('/saas/payment/check_completion', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({})
        })
        .then(response => response.json())
        .then(data => {
            console.log('SaaS payment check response:', data);
            
            if (data.success && data.redirect_url) {
                console.log('Redirecting to SaaS client:', data.redirect_url);
                
                // Show redirect message
                showRedirectMessage(data.redirect_url, data.client_name);
                
                // Redirect after a short delay
                setTimeout(function() {
                    window.location.href = data.redirect_url;
                }, 3000);
            }
        })
        .catch(error => {
            console.log('No SaaS redirect needed:', error);
        });
    }
    
    /**
     * Show redirect message to user
     */
    function showRedirectMessage(redirectUrl, clientName) {
        var messageDiv = document.createElement('div');
        messageDiv.className = 'saas_redirect_message';
        messageDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 15px 20px;
            border-radius: 5px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 9999;
            max-width: 350px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        `;
        
        messageDiv.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 5px;">
                <i class="fa fa-check-circle" style="margin-right: 8px;"></i>
                Payment Successful!
            </div>
            <div style="font-size: 14px;">
                Redirecting to your ${clientName || 'SaaS'} instance in 3 seconds...
            </div>
            <div style="margin-top: 8px; font-size: 12px; opacity: 0.9;">
                <a href="${redirectUrl}" style="color: white; text-decoration: underline;">
                    Go now →
                </a>
            </div>
        `;
        
        document.body.appendChild(messageDiv);
        
        // Remove message after redirect
        setTimeout(function() {
            if (messageDiv.parentNode) {
                messageDiv.parentNode.removeChild(messageDiv);
            }
        }, 4000);
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkPaymentCompletion);
    } else {
        checkPaymentCompletion();
    }
    
    // Also check after a delay to catch dynamic content
    setTimeout(checkPaymentCompletion, 2000);
    setTimeout(checkPaymentCompletion, 5000);
    
})();