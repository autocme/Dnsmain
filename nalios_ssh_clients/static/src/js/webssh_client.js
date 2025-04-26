// WebSSH Client JS - Simplified for Odoo 17
// This file provides the client-side functionality for WebSSH integration

(function() {
    let clientId = null;
    let commandHistory = [];
    let historyIndex = -1;
    let currentInput = '';
    
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
            hideLoading();
            return;
        }
        
        try {
            const sshInfo = JSON.parse(sshInfoElement.getAttribute('data-ssh-info') || '{}');
            clientId = sshInfo.id;
            
            // Check if we have valid SSH information
            if (!sshInfo.host || !sshInfo.username) {
                appendToTerminal("Error: Missing SSH host or username", "error");
                hideLoading();
                return;
            }
            
            appendToTerminal(`Connecting to ${sshInfo.username}@${sshInfo.host}...`, "info");
            
            // Execute a test command to verify connection
            executeCommand('echo "Connection successful"', function(result) {
                if (result.error) {
                    appendToTerminal("Connection error: " + result.error, "error");
                    updateConnectionStatus(false);
                } else {
                    // Connection successful
                    appendToTerminal("Connection established", "info");
                    updateConnectionStatus(true);
                    
                    // Show welcome message
                    appendToTerminal(`Welcome to ${sshInfo.host}`, "welcome");
                    appendToTerminal("Type commands below:", "info");
                }
                
                // Hide loading indicator
                hideLoading();
                
                // Setup command input
                setupCommandInput();
            });
            
        } catch (error) {
            console.error("Error parsing SSH info:", error);
            appendToTerminal("Error: Failed to parse SSH connection information", "error");
            hideLoading();
        }
    }
    
    /**
     * Execute SSH command via AJAX
     */
    function executeCommand(command, callback) {
        if (!clientId) {
            console.error("No client ID available");
            if (callback) callback({error: "No SSH client connection"});
            return;
        }
        
        // Execute command via Odoo's AJAX RPC
        const data = {
            client_id: clientId,
            command: command
        };
        
        // Use Odoo's AJAX call
        $.ajax({
            url: '/web/dataset/call_kw/ssh.client/exec_command',
            type: 'POST',
            dataType: 'json',
            contentType: 'application/json',
            data: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: {
                    model: 'ssh.client',
                    method: 'exec_command',
                    args: [clientId, command],
                    kwargs: {}
                },
                id: Math.floor(Math.random() * 1000000000)
            }),
            success: function(data) {
                if (data.error) {
                    console.error("Error executing command:", data.error);
                    if (callback) callback({error: data.error.data.message || "Unknown error"});
                } else {
                    if (callback) callback({success: true, result: data.result});
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.error("AJAX error:", textStatus, errorThrown);
                if (callback) callback({error: textStatus || "Network error"});
            }
        });
    }
    
    /**
     * Setup the command input field
     */
    function setupCommandInput() {
        const terminal = document.getElementById('terminal');
        
        // Create command input if it doesn't exist
        if (!terminal.querySelector('.input-line')) {
            const inputLine = document.createElement('div');
            inputLine.className = 'input-line';
            inputLine.innerHTML = '<span class="prompt">$ </span><span class="input" contenteditable="true" spellcheck="false"></span>';
            terminal.appendChild(inputLine);
            
            const inputSpan = inputLine.querySelector('.input');
            
            // Focus the input
            inputSpan.focus();
            
            // Handle key events
            inputSpan.addEventListener('keydown', function(e) {
                handleKeyDown(e, inputSpan);
            });
            
            // Focus input on terminal click
            terminal.addEventListener('click', function() {
                inputSpan.focus();
            });
        }
    }
    
    /**
     * Handle keyboard input
     */
    function handleKeyDown(e, inputElement) {
        if (e.key === 'Enter') {
            e.preventDefault();
            
            const command = inputElement.textContent;
            if (!command) return;
            
            // Add to history if not duplicate
            if (!commandHistory.length || commandHistory[commandHistory.length - 1] !== command) {
                commandHistory.push(command);
                if (commandHistory.length > 50) {
                    commandHistory.shift();
                }
            }
            historyIndex = -1;
            
            // Display command in terminal
            appendToTerminal('$ ' + command, 'command');
            
            // Clear input
            inputElement.textContent = '';
            
            // Execute command
            executeCommand(command, function(result) {
                if (result.error) {
                    appendToTerminal(result.error, "error");
                } else if (result.result) {
                    // Add result to terminal
                    // Check if it's HTML (from server-side formatting)
                    if (result.result.startsWith('<') && result.result.includes('</')) {
                        const wrapper = document.createElement('div');
                        wrapper.className = 'terminal-output';
                        wrapper.innerHTML = result.result;
                        const terminal = document.getElementById('terminal');
                        const inputLine = terminal.querySelector('.input-line');
                        if (inputLine) {
                            terminal.insertBefore(wrapper, inputLine);
                        } else {
                            terminal.appendChild(wrapper);
                        }
                    } else {
                        appendToTerminal(result.result, "output");
                    }
                }
                
                // Scroll to bottom
                const terminal = document.getElementById('terminal');
                terminal.scrollTop = terminal.scrollHeight;
            });
        }
        
        // History navigation
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            
            if (!commandHistory.length) return;
            
            // Save current input if starting navigation
            if (historyIndex === -1) {
                currentInput = inputElement.textContent;
            }
            
            historyIndex = Math.min(historyIndex + 1, commandHistory.length - 1);
            inputElement.textContent = commandHistory[commandHistory.length - 1 - historyIndex];
            moveCursorToEnd(inputElement);
            
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            
            if (historyIndex === -1) return;
            
            historyIndex--;
            
            if (historyIndex === -1) {
                inputElement.textContent = currentInput;
            } else {
                inputElement.textContent = commandHistory[commandHistory.length - 1 - historyIndex];
            }
            
            moveCursorToEnd(inputElement);
        }
    }
    
    /**
     * Move cursor to end of element
     */
    function moveCursorToEnd(el) {
        if (document.createRange) {
            const range = document.createRange();
            range.selectNodeContents(el);
            range.collapse(false);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
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
        
        // Convert ANSI codes to HTML (simplistic)
        text = processAnsiCodes(text);
        
        if (text.indexOf('<') >= 0 && text.indexOf('>') >= 0) {
            // Might be HTML, use innerHTML
            output.innerHTML = text;
        } else {
            output.textContent = text;
        }
        
        if (inputLine) {
            terminal.insertBefore(output, inputLine);
        } else {
            terminal.appendChild(output);
        }
        
        // Scroll to bottom
        terminal.scrollTop = terminal.scrollHeight;
    }
    
    /**
     * Process ANSI escape sequences
     */
    function processAnsiCodes(text) {
        if (!text) return '';
        
        // Very basic ANSI code handling
        return text.replace(/\x1B\[([0-9;]+)m/g, function(match, codes) {
            const params = codes.split(';');
            let result = '';
            
            for (let i = 0; i < params.length; i++) {
                const code = parseInt(params[i], 10);
                
                if (code === 0) {
                    result += '</span>';
                } else if (code === 1) {
                    result += '<span style="font-weight: bold;">';
                } else if (code === 31) {
                    result += '<span style="color: #ff6b6b;">';
                } else if (code === 32) {
                    result += '<span style="color: #56e356;">';
                } else if (code === 33) {
                    result += '<span style="color: #e3c456;">';
                } else if (code === 34) {
                    result += '<span style="color: #56a0e3;">';
                }
            }
            
            return result;
        });
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
            appendToTerminal('Reconnecting...', 'info');
            showLoading();
            initWebSSH();
        });
        
        // Disconnect button
        document.getElementById('disconnect-btn')?.addEventListener('click', function() {
            if (confirm('Are you sure you want to disconnect?')) {
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