// WebSSH Client JS
// This file provides the client-side functionality for WebSSH integration

(function() {
    // Wait for DOM to be fully loaded
    document.addEventListener('DOMContentLoaded', function() {
        // Initialize the WebSSH client
        initWebSSH();
        
        // Wire up UI event handlers
        setupEventHandlers();
    });
    
    /**
     * Initialize the WebSSH client
     */
    function initWebSSH() {
        // Get the terminal element
        const terminal = document.getElementById('terminal');
        if (!terminal) {
            console.error("Terminal element not found");
            return;
        }
        
        // Get SSH info from the data attribute
        const sshInfoElement = document.getElementById('ssh-info');
        if (!sshInfoElement) {
            console.error("SSH info element not found");
            appendToTerminal("Error: Missing SSH connection information", "error");
            return;
        }
        
        try {
            const sshInfo = JSON.parse(sshInfoElement.getAttribute('data-ssh-info') || '{}');
            
            // Check if we have valid SSH information
            if (!sshInfo.host || !sshInfo.username) {
                appendToTerminal("Error: Missing SSH host or username", "error");
                hideLoading();
                return;
            }
            
            appendToTerminal(`Connecting to ${sshInfo.username}@${sshInfo.host}...`, "info");
            
            // Get WebSocket URL
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/webssh/socket`;
            
            // Connect to WebSocket
            connectWebSocket(wsUrl, sshInfo);
            
        } catch (error) {
            console.error("Error parsing SSH info:", error);
            appendToTerminal("Error: Failed to parse SSH connection information", "error");
            hideLoading();
        }
    }
    
    /**
     * Connect to WebSocket for SSH communication
     */
    function connectWebSocket(url, sshInfo) {
        try {
            const socket = new WebSocket(url);
            
            socket.onopen = function() {
                console.log("WebSocket connection established");
                
                // Send SSH connection info
                socket.send(JSON.stringify({
                    type: 'connect',
                    data: {
                        host: sshInfo.host,
                        port: sshInfo.port,
                        username: sshInfo.username,
                        password: sshInfo.password || '',
                        privateKey: sshInfo.privateKey || '',
                        passphrase: sshInfo.passphrase || ''
                    }
                }));
                
                // Hide loading indicator
                hideLoading();
                
                // Update connection status
                updateConnectionStatus(true);
            };
            
            socket.onmessage = function(event) {
                const message = JSON.parse(event.data);
                
                if (message.error) {
                    appendToTerminal(message.error, "error");
                    updateConnectionStatus(false);
                } else if (message.data) {
                    appendToTerminal(message.data, "output");
                }
            };
            
            socket.onclose = function() {
                appendToTerminal("Connection closed", "info");
                updateConnectionStatus(false);
            };
            
            socket.onerror = function(error) {
                console.error("WebSocket error:", error);
                appendToTerminal("Connection error", "error");
                updateConnectionStatus(false);
                hideLoading();
            };
            
            // Store socket in a global variable for access from event handlers
            window.sshSocket = socket;
            
            // Setup command input
            setupCommandInput(socket);
            
        } catch (error) {
            console.error("Failed to connect to WebSocket:", error);
            appendToTerminal("Failed to connect: " + error.message, "error");
            updateConnectionStatus(false);
            hideLoading();
        }
    }
    
    /**
     * Setup the command input field
     */
    function setupCommandInput(socket) {
        const terminal = document.getElementById('terminal');
        
        // Create command input
        const inputLine = document.createElement('div');
        inputLine.className = 'input-line';
        inputLine.innerHTML = '<span class="prompt">$ </span><span class="input" contenteditable="true" spellcheck="false"></span>';
        terminal.appendChild(inputLine);
        
        const inputSpan = inputLine.querySelector('.input');
        
        // Focus the input
        inputSpan.focus();
        
        // Handle key events
        inputSpan.addEventListener('keydown', function(e) {
            handleKeyDown(e, inputSpan, socket);
        });
        
        // Focus input on terminal click
        terminal.addEventListener('click', function() {
            inputSpan.focus();
        });
    }
    
    /**
     * Handle keyboard input
     */
    function handleKeyDown(e, inputElement, socket) {
        if (e.key === 'Enter') {
            e.preventDefault();
            
            const command = inputElement.textContent;
            if (!command) return;
            
            // Display command in terminal
            appendToTerminal('$ ' + command, 'command');
            
            // Clear input
            inputElement.textContent = '';
            
            // Send command to server
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({
                    type: 'command',
                    data: command
                }));
            } else {
                appendToTerminal('Not connected to server', 'error');
            }
        }
    }
    
    /**
     * Append text to the terminal
     */
    function appendToTerminal(text, type) {
        const terminal = document.getElementById('terminal');
        const inputLine = terminal.querySelector('.input-line');
        
        const output = document.createElement('div');
        output.className = 'terminal-line';
        
        if (type) {
            output.classList.add('terminal-' + type);
        }
        
        output.textContent = text;
        
        if (inputLine) {
            terminal.insertBefore(output, inputLine);
        } else {
            terminal.appendChild(output);
        }
        
        // Scroll to bottom
        terminal.scrollTop = terminal.scrollHeight;
    }
    
    /**
     * Set up event handlers for various UI buttons
     */
    function setupEventHandlers() {
        // Clear button
        document.getElementById('clear-btn')?.addEventListener('click', function() {
            const terminal = document.getElementById('terminal');
            const inputLine = terminal.querySelector('.input-line');
            
            // Clear terminal content
            terminal.innerHTML = '';
            
            // Re-append input line if it exists
            if (inputLine) {
                terminal.appendChild(inputLine);
                inputLine.querySelector('.input')?.focus();
            }
        });
        
        // Reconnect button
        document.getElementById('reconnect-btn')?.addEventListener('click', function() {
            if (window.sshSocket) {
                window.sshSocket.close();
            }
            
            appendToTerminal('Reconnecting...', 'info');
            showLoading();
            initWebSSH();
        });
        
        // Disconnect button
        document.getElementById('disconnect-btn')?.addEventListener('click', function() {
            if (confirm('Are you sure you want to disconnect?')) {
                if (window.sshSocket) {
                    window.sshSocket.close();
                }
                window.location.href = '/web';
            }
        });
    }
    
    /**
     * Hide the loading indicator
     */
    function hideLoading() {
        const loading = document.getElementById('loading');
        if (loading) {
            loading.style.display = 'none';
        }
    }
    
    /**
     * Show the loading indicator
     */
    function showLoading() {
        const loading = document.getElementById('loading');
        if (loading) {
            loading.style.display = 'flex';
        }
    }
    
    /**
     * Update the connection status indicator
     */
    function updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        if (!statusElement) return;
        
        if (connected) {
            statusElement.innerHTML = '<span class="status connected"></span> Connected';
        } else {
            statusElement.innerHTML = '<span class="status disconnected"></span> Disconnected';
        }
    }
})();