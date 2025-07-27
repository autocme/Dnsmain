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
        var editableBtn = document.querySelector('.s_call_to_action a[role="button"]');

        if (startBtn) {
            startBtn.addEventListener('click', handleStartClick);
        }

        // Also handle clicks on the editable button in website editor mode
        if (editableBtn) {
            editableBtn.addEventListener('click', function(e) {
                e.preventDefault();
                // Trigger the hidden functional button
                if (startBtn) {
                    startBtn.click();
                }
            });
        }

        // Handle the new editable button class as well
        var editableStartBtn = document.querySelector('.saas_editable_start_btn');
        if (editableStartBtn) {
            editableStartBtn.addEventListener('click', function(e) {
                e.preventDefault();
                // Trigger the hidden functional button
                if (startBtn) {
                    startBtn.click();
                }
            });
        }

        if (continueBtn) {
            continueBtn.addEventListener('click', handleContinueClick);
        }

        // Note: PAY INVOICE NOW button handler is set up dynamically in showPaymentForm
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

    // Note: Duplicate handlePayInvoiceClick function removed
    // Payment handling is done through setupInvoicePaymentButton/openNativeOdooPaymentWizard

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
     * Show deployment monitoring screen with job queue tracking
     */
    function showDeploymentMonitoring(clientId, clientDomain, isFreeTrial) {
        // Hide current loading screen
        hideLoadingScreen();
        
        // Create full-screen deployment overlay
        var deploymentOverlay = document.createElement('div');
        deploymentOverlay.id = 'saasDeploymentOverlay';
        deploymentOverlay.className = 'saas_deployment_overlay';
        deploymentOverlay.innerHTML = `
            <div class="saas_deployment_content">
                <div class="saas_deployment_icon">
                    <i class="fa fa-cogs fa-spin" aria-hidden="true"></i>
                </div>
                <h3>${isFreeTrial ? '🎉 Free Trial Activated!' : '💳 Payment Successful!'}</h3>
                <p id="deploymentStatusText">We are creating your system and you'll be redirected after finish</p>
                <div class="saas_loading_dots">
                    <div class="dot"></div>
                    <div class="dot"></div>
                    <div class="dot"></div>
                </div>
                <div id="deploymentError" class="saas_deployment_error" style="display: none;">
                    <i class="fa fa-exclamation-triangle"></i>
                    <p>System creation failed. Please contact support for assistance.</p>
                </div>
            </div>
        `;
        
        // Full viewport coverage styles
        deploymentOverlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: linear-gradient(135deg, #2F3349 0%, #1a1e30 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 99999;
            color: white;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        `;
        
        // Prevent body scrolling while overlay is shown
        document.body.style.overflow = 'hidden';
        
        document.body.appendChild(deploymentOverlay);
        
        // Make overlay visible immediately (force show)
        deploymentOverlay.style.opacity = '1';
        deploymentOverlay.style.display = 'flex';
        
        // Start monitoring deployment status
        monitorDeploymentStatus(clientId, clientDomain);
        
        console.log('Deployment overlay added to DOM and should cover entire screen');
    }
    
    /**
     * Monitor deployment status using job queue
     */
    function monitorDeploymentStatus(clientId, clientDomain) {
        console.log('Starting deployment monitoring for client:', clientId);
        
        var checkInterval = setInterval(function() {
            fetch('/saas/client/deployment_status/' + clientId, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {}
                })
            })
            .then(function(response) {
                return response.json();
            })
            .then(function(data) {
                if (data.result) {
                    var status = data.result.status;
                    var message = data.result.message || 'Deployment in progress...';
                    
                    console.log('Deployment status response:', JSON.stringify(data.result));
                    console.log('Deployment status:', status, 'Message:', message);
                    
                    // Update status text only for non-error states (errors handled below)
                    var statusText = document.getElementById('deploymentStatusText');
                    if (statusText && status !== 'failed' && status !== 'cancel' && status !== 'cancelled') {
                        statusText.textContent = message;
                    }
                    
                    if (status === 'completed' && data.result.deployment_complete) {
                        // Deployment completed successfully
                        clearInterval(checkInterval);
                        console.log('Deployment completed, redirecting to:', clientDomain);
                        
                        // Show success message briefly then redirect
                        if (statusText) {
                            statusText.textContent = 'Deployment completed! Redirecting...';
                        }
                        
                        setTimeout(function() {
                            // Restore body overflow before redirect
                            document.body.style.overflow = '';
                            
                            var redirectUrl = clientDomain || '/web';
                            
                            // Ensure clean URL format
                            if (redirectUrl !== '/web' && !redirectUrl.startsWith('http')) {
                                redirectUrl = `https://${redirectUrl}`;
                            }
                            
                            console.log('Redirecting to SaaS instance:', redirectUrl);
                            window.location.href = redirectUrl;
                        }, 2000);
                        
                    } else if (status === 'failed' || status === 'cancel' || status === 'cancelled') {
                        // Deployment failed or cancelled
                        clearInterval(checkInterval);
                        console.error('System creation failed or cancelled, status:', status);
                        
                        // Hide loading elements and show error
                        var deploymentIcon = document.querySelector('.saas_deployment_icon i');
                        var loadingDots = document.querySelector('.saas_loading_dots');
                        var errorDiv = document.getElementById('deploymentError');
                        
                        if (deploymentIcon) {
                            deploymentIcon.className = 'fa fa-exclamation-triangle';
                            deploymentIcon.style.color = '#e74c3c';
                        }
                        if (loadingDots) {
                            loadingDots.style.display = 'none';
                        }
                        if (errorDiv) {
                            errorDiv.style.display = 'block';
                        }
                        if (statusText) {
                            statusText.textContent = 'System creation failed. Please contact support for assistance.';
                        }
                        
                        // Restore body overflow on failure
                        document.body.style.overflow = '';
                    }
                    // For 'deploying', 'pending' statuses, continue monitoring
                } else {
                    console.error('Invalid response from deployment status check:', data);
                }
            })
            .catch(function(error) {
                console.error('Error checking deployment status:', error);
                // Continue monitoring despite errors
            });
        }, 3000); // Check every 3 seconds
        
        // Safety timeout after 10 minutes
        setTimeout(function() {
            clearInterval(checkInterval);
            console.log('Deployment monitoring timeout after 10 minutes');
        }, 600000);
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

        // Store result data for success screen
        window.saasClientResult = result;

        // Handle free trial vs paid packages differently
        if (result.is_free_trial) {
            // For free trial: monitor deployment and redirect when complete
            console.log('Free trial created, monitoring deployment for client:', result.client_id);
            
            // Don't hide loading screen - let showDeploymentMonitoring handle the transition
            // Show deployment monitoring screen immediately
            showDeploymentMonitoring(result.client_id, result.client_domain, true);
        } else {
            // For paid packages: hide loading and show payment form (already embedded)
            hideLoadingScreen();
            setTimeout(function() {
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
     * Open Odoo's built-in invoice payment wizard directly as modal
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
                console.log('Invoice info retrieved, opening native payment wizard...');

                // Use Odoo's native payment wizard via JSON-RPC
                openNativeOdooPaymentWizard(data.invoice_id, clientId);
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
     * Generate and redirect to payment link for invoice
     */
    function openNativeOdooPaymentWizard(invoiceId, clientId) {
        console.log('Generating payment link for invoice:', invoiceId, 'client:', clientId);

        // Call our controller to get the payment wizard action
        fetch('/saas/client/open_payment_wizard', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: {
                    client_id: clientId
                },
                id: new Date().getTime()
            })
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            console.log('Payment link response:', data);

            if (data.result && data.result.success && data.result.payment_link) {
                console.log('Payment link generated:', data.result.payment_link);

                // Redirect to the payment link (same window for better UX)
                window.location.href = data.result.payment_link;

            } else {
                console.error('Failed to generate payment link. Full response:', data);
                console.error('Error details:', data.result ? data.result.error : 'No result in response');

                var errorMsg = 'Unable to generate payment link';
                if (data.result && data.result.error) {
                    errorMsg += ': ' + data.result.error;
                } else if (data.error) {
                    errorMsg += ': ' + (data.error.message || data.error);
                } else {
                    errorMsg += '. Please try again.';
                }

                showErrorMessage(errorMsg);
            }
        })
        .catch(function(error) {
            console.error('Error opening payment wizard:', error);
            showErrorMessage('Error opening payment wizard. Please try again.');
        });
    }

    /**
     * Try to open action using Odoo's action manager
     */
    function tryOpenWithOdooActionManager(action, clientId) {
        try {
            // Method 1: Check for Odoo action manager in current window
            if (window.odoo && window.odoo.__DEBUG__ && window.odoo.__DEBUG__.services) {
                var actionService = window.odoo.__DEBUG__.services['action'];
                if (actionService) {
                    console.log('Using Odoo action service...');
                    actionService.doAction(action, {
                        onClose: function() {
                            console.log('Payment wizard closed, checking status...');
                            setTimeout(function() {
                                checkPaymentStatus(clientId);
                            }, 1500);
                        }
                    });
                    return true;
                }
            }

            // Method 2: Check for parent window Odoo
            if (window.parent && window.parent.odoo && window.parent.odoo.action_manager) {
                console.log('Using parent Odoo action manager...');
                window.parent.odoo.action_manager.do_action(action, {
                    on_close: function() {
                        console.log('Payment wizard closed, checking status...');
                        setTimeout(function() {
                            checkPaymentStatus(clientId);
                        }, 1500);
                    }
                });
                return true;
            }

            // Method 3: Try current window action manager
            if (window.odoo && window.odoo.action_manager) {
                console.log('Using current window action manager...');
                window.odoo.action_manager.do_action(action, {
                    on_close: function() {
                        console.log('Payment wizard closed, checking status...');
                        setTimeout(function() {
                            checkPaymentStatus(clientId);
                        }, 1500);
                    }
                });
                return true;
            }

        } catch (e) {
            console.log('Could not use Odoo action manager:', e);
        }

        return false; // No action manager available
    }

    /**
     * Show payment redirect info when action manager is not available
     */
    function showPaymentRedirectInfo(invoiceId, paymentData, clientId) {
        console.log('Showing payment redirect info for invoice:', invoiceId, 'with data:', paymentData);

        // Safe access to payment data with fallbacks
        var amount = paymentData.invoice_amount || paymentData.amount || '0.00';
        var currency = paymentData.invoice_currency || paymentData.currency || '$';
        var invoiceName = paymentData.invoice_name || `Invoice ${invoiceId}`;

        // Show message about redirecting to payment
        var messageHtml = `
            <div class="alert alert-info" style="margin: 20px 0;">
                <h5><i class="fa fa-credit-card"></i> Ready to Pay</h5>
                <p>Your invoice for <strong>${currency} ${amount}</strong> is ready for payment.</p>
                <p>Click the button below to complete your payment using Odoo's secure payment system.</p>
                <div style="text-align: center; margin-top: 20px;">
                    <a href="/my/invoices/${invoiceId}" target="_blank" class="btn btn-primary btn-lg" style="background-color: #875A7B; border-color: #875A7B; padding: 15px 30px;">
                        <i class="fa fa-external-link"></i> Pay ${invoiceName}
                    </a>
                </div>
                <p style="margin-top: 15px; text-align: center; color: #666;">
                    <small>After payment completion, return to this page or check your email for confirmation.</small>
                </p>
            </div>
        `;

        // Replace payment info section with redirect message
        var paymentInfo = document.getElementById('saasPaymentInfo');
        if (paymentInfo) {
            paymentInfo.innerHTML = messageHtml;

            // Payment status is now handled automatically by backend
            // No need for manual polling - invoice payment triggers automatic deployment
        }
    }

    /**
     * Open Odoo's native payment wizard as modal dialog
     */
    function openPaymentWizardModal(invoiceId, accessToken, clientId, amount, currency) {
        console.log('Opening Odoo native payment wizard as modal...');

        // Try to use Odoo's web framework to open the native payment wizard
        if (typeof odoo !== 'undefined' && odoo.define) {
            // Use Odoo's modal system
            openOdooNativePaymentModal(invoiceId, accessToken, clientId);
        } else {
            // Fallback: Load the actual invoice portal payment wizard in an iframe
            openInvoicePortalModal(invoiceId, accessToken, clientId);
        }
    }

    /**
     * Open native Odoo payment modal using Odoo's web framework
     */
    function openOdooNativePaymentModal(invoiceId, accessToken, clientId) {
        console.log('Using Odoo native payment modal...');

        try {
            // Import Odoo's Dialog component and open payment wizard
            if (window.parent && window.parent.odoo) {
                // We're in an iframe, use parent's odoo
                var parentOdoo = window.parent.odoo;
                parentOdoo.define('saas.payment.modal', function(require) {
                    var Dialog = require('web.Dialog');
                    var core = require('web.core');
                    var rpc = require('web.rpc');

                    // Create payment wizard action
                    return rpc.query({
                        model: 'account.move',
                        method: 'action_register_payment',
                        args: [parseInt(invoiceId)],
                        context: {
                            'saas_client_id': clientId,
                            'saas_modal': true
                        }
                    }).then(function(action) {
                        // Open the action in a dialog
                        return parentOdoo.action_manager.do_action(action, {
                            on_close: function() {
                                console.log('Payment wizard closed, checking payment status...');
                                setTimeout(function() {
                                    checkPaymentStatus(clientId);
                                }, 1500);
                            }
                        });
                    });
                });
            } else {
                // Fallback to iframe approach
                openInvoicePortalModal(invoiceId, accessToken, clientId);
            }
        } catch (e) {
            console.log('Native Odoo modal failed, using iframe approach:', e);
            openInvoicePortalModal(invoiceId, accessToken, clientId);
        }
    }

    /**
     * Open invoice portal payment wizard in modal iframe
     */
    function openInvoicePortalModal(invoiceId, accessToken, clientId) {
        console.log('Opening invoice portal in modal iframe...');

        // Create modal backdrop matching Odoo's native style
        var modalBackdrop = document.createElement('div');
        modalBackdrop.className = 'modal fade show';
        modalBackdrop.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.4);
            z-index: 1050;
            display: block;
        `;

        // Create modal dialog matching Odoo's native payment wizard
        var modalDialog = document.createElement('div');
        modalDialog.className = 'modal-dialog modal-lg';
        modalDialog.style.cssText = `
            margin: 30px auto;
            max-width: 600px;
            width: calc(100% - 60px);
        `;

        // Modal content
        var modalContent = document.createElement('div');
        modalContent.className = 'modal-content';
        modalContent.style.cssText = `
            background-color: #fff;
            border: 1px solid rgba(0,0,0,0.2);
            border-radius: 6px;
            box-shadow: 0 3px 9px rgba(0,0,0,0.5);
            background-clip: padding-box;
        `;

        // Build the exact modal structure from the screenshot
        modalContent.innerHTML = `
            <div class="modal-header" style="padding: 20px 24px; border-bottom: 1px solid #e5e5e5; background-color: #f8f9fa;">
                <h4 class="modal-title" style="margin: 0; font-size: 24px; font-weight: 600; color: #212529;">Pay with</h4>
                <button type="button" class="btn-close saas_close_modal" style="background: none; border: none; font-size: 28px; cursor: pointer; color: #999; padding: 0; margin: -10px -10px -10px auto;">×</button>
            </div>
            <div class="modal-body" style="padding: 0; position: relative; height: 500px;">
                <iframe id="saasPaymentFrame" 
                        src="/my/invoices/${invoiceId}?access_token=${accessToken || ''}&modal=1" 
                        style="width: 100%; height: 100%; border: none; border-radius: 0 0 6px 6px;"
                        onload="handlePaymentFrameLoad(this, '${clientId}')">
                </iframe>
            </div>
        `;

        modalDialog.appendChild(modalContent);
        modalBackdrop.appendChild(modalDialog);
        document.body.appendChild(modalBackdrop);

        // Close modal functionality
        var closeBtn = modalContent.querySelector('.saas_close_modal');
        closeBtn.addEventListener('click', function() {
            document.body.removeChild(modalBackdrop);
        });

        modalBackdrop.addEventListener('click', function(e) {
            if (e.target === modalBackdrop) {
                document.body.removeChild(modalBackdrop);
            }
        });

        // Store reference for frame communication
        window.saasPaymentModal = {
            backdrop: modalBackdrop,
            clientId: clientId
        };
    }

    /**
     * Global function to handle payment frame load
     */
    window.handlePaymentFrameLoad = function(iframe, clientId) {
        console.log('Payment iframe loaded for client:', clientId);

        try {
            // Add styles to make the iframe content look seamless
            var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            var style = iframeDoc.createElement('style');
            style.textContent = `
                .o_portal_navbar, .o_portal_breadcrumb, .o_portal_sidebar { display: none !important; }
                .o_portal_wrap { padding: 0 !important; margin: 0 !important; }
                body { background: transparent !important; margin: 0 !important; padding: 20px !important; }
                .container { max-width: none !important; padding: 0 !important; }
                .card { border: none !important; box-shadow: none !important; }
                .card-header { display: none !important; }
            `;
            iframeDoc.head.appendChild(style);

            // Monitor for payment completion
            var checkInterval = setInterval(function() {
                try {
                    var currentUrl = iframe.contentWindow.location.href;
                    console.log('Current iframe URL:', currentUrl);

                    // Check if payment was successful (redirect to success page)
                    if (currentUrl.includes('/payment/status') || 
                        currentUrl.includes('/payment/confirm') ||
                        currentUrl.includes('payment_success')) {

                        console.log('Payment completed, closing modal...');
                        clearInterval(checkInterval);

                        // Close modal
                        if (window.saasPaymentModal && window.saasPaymentModal.backdrop) {
                            document.body.removeChild(window.saasPaymentModal.backdrop);
                        }

                        // Payment completion handled automatically by backend
                        console.log('Payment completed - backend will handle deployment automatically');
                    }
                } catch (e) {
                    // Cross-origin issues, ignore
                }
            }, 1000);

            // Stop monitoring after 10 minutes
            setTimeout(function() {
                clearInterval(checkInterval);
            }, 600000);

        } catch (e) {
            console.log('Could not modify iframe content due to cross-origin restrictions:', e);
        }
    };

    /**
     * Handle payment form submission within modal
     */
    function handleModalPaymentSubmission(form, clientId, modalBackdrop) {
        console.log('Handling payment form submission in modal...');

        // Show loading state
        var submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
        var originalText = submitBtn ? submitBtn.textContent : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Processing...';
        }

        // Create form data
        var formData = new FormData(form);

        // Submit payment form
        fetch(form.action || '/payment/transaction', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(function(response) {
            if (response.ok) {
                console.log('Payment submitted successfully, closing modal and checking status...');

                // Close modal
                if (modalBackdrop && modalBackdrop.parentElement) {
                    modalBackdrop.parentElement.removeChild(modalBackdrop);
                }

                // Payment completion handled automatically by backend
                console.log('Payment submitted - backend will handle deployment automatically');

            } else {
                throw new Error('Payment submission failed: ' + response.status);
            }
        })
        .catch(function(error) {
            console.error('Payment submission error:', error);

            // Restore submit button
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }

            // Show error message
            showErrorMessage('Payment failed. Please try again.');
        });
    }

    /**
     * Payment status now handled automatically by backend when invoice is paid
     * No need for manual checking - payment completion triggers automatic deployment
     */

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

    /**
     * Handle successful payment redirect
     */
    function handlePaymentRedirect(paymentLink) {
        console.log('Redirecting to payment:', paymentLink);

        // Create redirect message
        var messageHtml = `
            <div class="saas_payment_redirect">
                <div class="alert alert-info text-center">
                    <h5><i class="fa fa-credit-card"></i> Processing Payment</h5>
                    <p>You are being redirected to complete your payment...</p>
                    <div class="saas_loading_spinner">
                        <div class="saas_spinner"></div>
                    </div>
                </div>
                <p style="margin-top: 15px; text-align: center; color: #666;">
                    <small>After payment completion, you will be automatically redirected to your SaaS instance.</small>
                </p>
                <div class="alert alert-success" style="margin-top: 15px;">
                    <i class="fa fa-info-circle"></i>
                    <strong>What happens next:</strong>
                    <ol style="margin-top: 10px; margin-bottom: 0;">
                        <li>Complete payment in the new window</li>
                        <li>Your SaaS instance will be deployed automatically</li>
                        <li>You'll be redirected to your instance URL</li>
                    </ol>
                </div>
            </div>
        `;

        // Replace payment info section with redirect message
        var paymentInfo = document.getElementById('saasPaymentInfo');
        if (paymentInfo) {
            paymentInfo.innerHTML = messageHtml;
        }

        // Open payment in new window and monitor for completion
        var paymentWindow = window.open(paymentLink, '_blank');

        // Optional: Check if payment window is closed (user might have completed payment)
        var checkClosed = setInterval(function() {
            if (paymentWindow.closed) {
                clearInterval(checkClosed);
                console.log('Payment window closed - payment may be completed');
                // Show completion message
                if (paymentInfo) {
                    paymentInfo.innerHTML = `
                        <div class="alert alert-info text-center">
                            <i class="fa fa-hourglass-half"></i>
                            <strong>Payment Processing...</strong>
                            <p>Please wait while we verify your payment and prepare your instance.</p>
                            <p><small>You will be redirected automatically once processing is complete.</small></p>
                        </div>
                    `;
                }
            }
        }, 1000);
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPurchaseConfirm);
    } else {
        initPurchaseConfirm();
    }

})();