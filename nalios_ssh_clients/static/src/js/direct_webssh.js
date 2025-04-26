// Direct WebSSH implementation using AJAX - no WebSockets required
// This is a simplified version for Odoo 17 compatibility

document.addEventListener('DOMContentLoaded', function() {
    let clientId = null;
    let commandHistory = [];
    let historyIndex = -1;
    let currentInput = '';
    let inputLine = null;
    
    const terminal = document.getElementById('terminal');
    const statusIndicator = document.getElementById('connection-status');
    const sshInfoElement = document.getElementById('ssh-info');
    
    if (!terminal || !sshInfoElement) {
        console.error("Required elements not found");
        return;
    }
    
    // Initialize the terminal
    init();
    
    function init() {
        // Setup terminal
        terminal.innerHTML = '<div class="terminal-welcome">Connecting to SSH server...</div>';
        
        try {
            // Get connection info from the data attribute
            const sshInfo = JSON.parse(sshInfoElement.getAttribute('data-ssh-info') || '{}');
            clientId = sshInfo.id;
            
            if (!sshInfo.host || !sshInfo.username) {
                appendToTerminal("Error: Missing SSH connection information", "error");
                updateStatus(false);
                createCommandInput();
                return;
            }
            
            // Execute test command to check connection
            executeCommand('echo "Connected to SSH server"', function(result) {
                if (result.error) {
                    appendToTerminal("Connection error: " + result.error, "error");
                    updateStatus(false);
                } else {
                    // Connection successful
                    appendToTerminal("Connected to " + sshInfo.username + "@" + sshInfo.host, "info");
                    updateStatus(true);
                    
                    // Show welcome message
                    appendToTerminal("Type commands below:", "info");
                }
                
                // Create command input
                createCommandInput();
            });
        } catch (error) {
            appendToTerminal("Error parsing SSH info: " + error.message, "error");
            updateStatus(false);
            createCommandInput();
        }
        
        // Setup button handlers
        setupButtonHandlers();
    }
    
    function createCommandInput() {
        // Create input line if it doesn't exist
        if (!inputLine) {
            inputLine = document.createElement('div');
            inputLine.className = 'input-line';
            inputLine.innerHTML = '<span class="prompt">$ </span><span class="input" contenteditable="true" spellcheck="false"></span>';
            terminal.appendChild(inputLine);
            
            const inputSpan = inputLine.querySelector('.input');
            
            // Focus input
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
    
    function executeCommand(command, callback) {
        if (!clientId) {
            console.error("No client ID available");
            if (callback) callback({error: "No SSH client connection"});
            return;
        }
        
        // Execute command via Odoo's AJAX RPC
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
                    if (callback) callback({error: data.error.data?.message || "Unknown error"});
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
    
    function handleKeyDown(e, inputElement) {
        if (e.key === 'Enter') {
            e.preventDefault();
            const command = inputElement.textContent;
            if (!command) return;
            
            // Add to history
            if (!commandHistory.length || commandHistory[0] !== command) {
                commandHistory.unshift(command);
                if (commandHistory.length > 50) {
                    commandHistory.pop();
                }
            }
            historyIndex = -1;
            
            // Display command
            appendToTerminal('$ ' + command, 'command');
            
            // Clear input
            inputElement.textContent = '';
            
            // Execute command
            executeCommand(command, function(result) {
                if (result.error) {
                    appendToTerminal(result.error, "error");
                } else if (result.result) {
                    // Check if it's HTML (from server-side formatting)
                    if (result.result.startsWith('<') && result.result.includes('</')) {
                        const wrapper = document.createElement('div');
                        wrapper.className = 'terminal-output';
                        wrapper.innerHTML = result.result;
                        terminal.insertBefore(wrapper, inputLine);
                    } else {
                        appendToTerminal(result.result, "output");
                    }
                }
                
                // Scroll to bottom
                scrollToBottom();
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
            
            historyIndex++;
            if (historyIndex >= commandHistory.length) {
                historyIndex = commandHistory.length - 1;
            }
            
            inputElement.textContent = commandHistory[historyIndex];
            moveCursorToEnd(inputElement);
            
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            
            if (historyIndex === -1) return;
            
            historyIndex--;
            
            if (historyIndex === -1) {
                inputElement.textContent = currentInput;
            } else {
                inputElement.textContent = commandHistory[historyIndex];
            }
            
            moveCursorToEnd(inputElement);
        }
        
        // Ctrl+C to cancel
        if (e.key === 'c' && e.ctrlKey) {
            if (window.getSelection().toString()) {
                // If text is selected, let the browser handle the copy
                return;
            }
            
            appendToTerminal('^C', 'command');
            inputElement.textContent = '';
        }
    }
    
    function appendToTerminal(text, type) {
        if (!text) return;
        
        const output = document.createElement('div');
        output.className = 'terminal-line';
        
        if (type) {
            output.classList.add(`terminal-${type}`);
        }
        
        // Process ANSI codes
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
        
        scrollToBottom();
    }
    
    function processAnsiCodes(text) {
        if (!text) return '';
        
        // Simple ANSI code processing
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
    
    function setupButtonHandlers() {
        // Reconnect button
        document.getElementById('reconnect-btn')?.addEventListener('click', function() {
            appendToTerminal("Reconnecting...", "info");
            // Execute test command to check if connection is alive
            executeCommand('echo "Reconnection test"', function(result) {
                if (result.error) {
                    appendToTerminal("Reconnection failed: " + result.error, "error");
                    updateStatus(false);
                } else {
                    appendToTerminal("Reconnected successfully", "info");
                    updateStatus(true);
                }
            });
        });
        
        // Clear button
        document.getElementById('clear-btn')?.addEventListener('click', function() {
            // Keep only the input line
            terminal.innerHTML = '';
            if (inputLine) {
                terminal.appendChild(inputLine);
                inputLine.querySelector('.input')?.focus();
            } else {
                createCommandInput();
            }
        });
        
        // Disconnect button
        document.getElementById('disconnect-btn')?.addEventListener('click', function() {
            if (confirm('Are you sure you want to disconnect?')) {
                window.location.href = '/web';
            }
        });
        
        // Fullscreen button
        document.getElementById('fullscreen-btn')?.addEventListener('click', function() {
            if (terminal.requestFullscreen) {
                terminal.requestFullscreen();
            } else if (terminal.mozRequestFullScreen) {
                terminal.mozRequestFullScreen();
            } else if (terminal.webkitRequestFullscreen) {
                terminal.webkitRequestFullscreen();
            } else if (terminal.msRequestFullscreen) {
                terminal.msRequestFullscreen();
            }
        });
    }
    
    function updateStatus(isConnected) {
        if (statusIndicator) {
            if (isConnected) {
                statusIndicator.innerHTML = '<span class="status connected"></span> Connected';
            } else {
                statusIndicator.innerHTML = '<span class="status disconnected"></span> Disconnected';
            }
        }
    }
    
    function scrollToBottom() {
        terminal.scrollTop = terminal.scrollHeight;
    }
    
    function moveCursorToEnd(element) {
        if (document.createRange) {
            const range = document.createRange();
            range.selectNodeContents(element);
            range.collapse(false);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
        }
    }
});