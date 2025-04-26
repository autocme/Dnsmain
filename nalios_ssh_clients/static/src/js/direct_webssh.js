// Direct WebSSH implementation using web sockets
// This is a simplified version that doesn't require the webssh package

document.addEventListener('DOMContentLoaded', function() {
    const terminal = document.getElementById('terminal');
    const statusIndicator = document.getElementById('connection-status');
    const sshInfoElement = document.getElementById('ssh-info');
    
    if (!terminal || !sshInfoElement) {
        console.error("Required elements not found");
        return;
    }
    
    // Get connection info from the data attribute
    const sshInfo = JSON.parse(sshInfoElement.getAttribute('data-ssh-info') || '{}');
    
    if (!sshInfo.host || !sshInfo.port || !sshInfo.username) {
        appendToTerminal("Error: Missing SSH connection information", "error");
        return;
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/webssh/socket`;
    
    let socket = null;
    let connected = false;
    let commandHistory = [];
    let historyIndex = -1;
    let currentInput = '';
    let inputLine = null;
    
    function init() {
        // Setup terminal
        terminal.innerHTML = '<div class="terminal-welcome">Connecting to SSH server...</div>';
        terminal.style.height = 'calc(100% - 30px)';
        terminal.style.padding = '10px';
        terminal.style.overflow = 'auto';
        terminal.style.fontFamily = "'JetBrains Mono', monospace";
        terminal.style.whiteSpace = 'pre-wrap';
        terminal.style.fontSize = '14px';
        terminal.style.lineHeight = '1.5';
        
        // Create input line
        inputLine = document.createElement('div');
        inputLine.className = 'input-line';
        inputLine.innerHTML = '<span class="prompt">$ </span><span class="input" contenteditable="true" spellcheck="false"></span>';
        terminal.appendChild(inputLine);
        
        // Get the editable span
        const inputSpan = inputLine.querySelector('.input');
        
        // Focus on click
        terminal.addEventListener('click', function() {
            inputSpan.focus();
        });
        
        // Handle key events
        inputSpan.addEventListener('keydown', function(e) {
            handleKeyDown(e, inputSpan);
        });
        
        // Start WebSocket connection
        connectWebSocket();
    }
    
    function connectWebSocket() {
        if (socket) {
            socket.close();
        }
        
        try {
            socket = new WebSocket(wsUrl);
            
            socket.onopen = function() {
                console.log("WebSocket connection established");
                // Send initial connection info
                sendConnectionInfo();
            };
            
            socket.onmessage = function(event) {
                const data = JSON.parse(event.data);
                
                if (data.error) {
                    appendToTerminal(data.error, "error");
                    updateStatus(false);
                }
                
                if (data.data) {
                    appendToTerminal(data.data, "response");
                }
                
                if (data.status === 'connected') {
                    connected = true;
                    updateStatus(true);
                    appendToTerminal("Connected to " + sshInfo.username + "@" + sshInfo.host, "info");
                    appendToTerminal("Type commands below:", "info");
                    scrollToBottom();
                }
                
                if (data.status === 'disconnected') {
                    connected = false;
                    updateStatus(false);
                    appendToTerminal("Disconnected from server", "error");
                }
            };
            
            socket.onclose = function() {
                connected = false;
                updateStatus(false);
                appendToTerminal("Connection closed", "error");
            };
            
            socket.onerror = function(error) {
                connected = false;
                updateStatus(false);
                appendToTerminal("WebSocket error: " + error.message, "error");
                console.error("WebSocket error:", error);
            };
            
        } catch (error) {
            appendToTerminal("Failed to connect: " + error.message, "error");
            console.error("Failed to create WebSocket:", error);
        }
    }
    
    function sendConnectionInfo() {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                type: 'connection',
                data: {
                    host: sshInfo.host,
                    port: parseInt(sshInfo.port),
                    username: sshInfo.username,
                    password: sshInfo.password || '',
                    privateKey: sshInfo.privateKey || '',
                    passphrase: sshInfo.passphrase || ''
                }
            }));
        }
    }
    
    function sendCommand(command) {
        if (!command || !command.trim()) return;
        
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                type: 'command',
                data: command
            }));
            
            // Add to history if not duplicate
            if (!commandHistory.length || commandHistory[0] !== command) {
                commandHistory.unshift(command);
                if (commandHistory.length > 50) {
                    commandHistory.pop();
                }
            }
            
            historyIndex = -1;
        } else {
            appendToTerminal("Not connected to server", "error");
        }
    }
    
    function handleKeyDown(e, inputElement) {
        if (e.key === 'Enter') {
            e.preventDefault();
            const command = inputElement.textContent;
            
            // Create command display
            appendToTerminal('$ ' + command, 'command');
            
            // Clear input
            inputElement.textContent = '';
            
            // Send command
            sendCommand(command);
            
            return;
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
        
        // Tab completion (just for demo)
        if (e.key === 'Tab') {
            e.preventDefault();
            // Add a simple tab completion if needed
        }
        
        // Ctrl+C to interrupt
        if (e.key === 'c' && e.ctrlKey) {
            if (window.getSelection().toString()) {
                // If text is selected, let the browser handle the copy
                return;
            }
            
            socket.send(JSON.stringify({
                type: 'signal',
                data: 'SIGINT'
            }));
            
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
        
        // Process ANSI codes and colorize
        text = processAnsiCodes(text);
        
        output.innerHTML = text;
        terminal.insertBefore(output, inputLine);
        scrollToBottom();
    }
    
    function processAnsiCodes(text) {
        // Very simple ANSI code processing - in a real app, use a proper library
        return text.replace(/\x1B\[([0-9;]+)m/g, function(match, p1) {
            // This is a simplified version - would need more complex handling for real terminal
            if (p1 === '0') return '</span>';
            if (p1 === '31') return '<span style="color: #ff6b6b;">';
            if (p1 === '32') return '<span style="color: #56e356;">';
            if (p1 === '33') return '<span style="color: #ffc107;">';
            if (p1 === '34') return '<span style="color: #56a0e3;">';
            if (p1 === '37') return '<span style="color: #ffffff;">';
            return '';
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
        const range = document.createRange();
        const selection = window.getSelection();
        range.selectNodeContents(element);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
    }
    
    // Button event handlers
    document.getElementById('reconnect-btn')?.addEventListener('click', function() {
        appendToTerminal("Reconnecting...", "info");
        connectWebSocket();
    });
    
    document.getElementById('clear-btn')?.addEventListener('click', function() {
        // Remove all elements except the input line
        while (terminal.firstChild !== inputLine) {
            terminal.removeChild(terminal.firstChild);
        }
    });
    
    document.getElementById('disconnect-btn')?.addEventListener('click', function() {
        if (confirm('Are you sure you want to disconnect?')) {
            if (socket) {
                socket.close();
            }
            window.location.href = '/web';
        }
    });
    
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
    
    // Start the client
    init();
});