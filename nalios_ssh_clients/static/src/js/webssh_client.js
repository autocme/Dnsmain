// WebSSH Client JavaScript for Odoo integration

/**
 * Initialize a WebSSH client using a WebSocket connection
 * @param {String} socketUrl - The WebSocket URL to connect to
 */
function initWebSSHClient(socketUrl) {
    // Check if URL is provided
    if (!socketUrl) {
        console.error("WebSocket URL not provided");
        displayError("WebSocket URL not provided");
        return;
    }

    // Terminal elements
    const terminal = document.getElementById('terminal');
    const loadingIndicator = document.getElementById('loading');
    
    // Status indicators
    const statusContainer = document.getElementById('connection-status');
    let socket = null;
    let isConnected = false;
    
    // Terminal settings
    const terminalSettings = {
        fontSize: 14,
        fontFamily: "'JetBrains Mono', 'SF Mono', 'Monaco', 'Menlo', 'Courier New', monospace",
        cursorBlink: true,
        cursorStyle: 'block',
        theme: {
            background: '#232f3e',
            foreground: '#f0f0f0',
            cursor: '#ff9900',
            selection: 'rgba(255, 153, 0, 0.3)',
            black: '#000000',
            red: '#ff6b6b',
            green: '#56e356',
            yellow: '#ffc107',
            blue: '#56a0e3',
            magenta: '#d951ff',
            cyan: '#4fc1ff',
            white: '#ffffff',
            brightBlack: '#656565',
            brightRed: '#ff8f8f',
            brightGreen: '#72ff72',
            brightYellow: '#ffd54f',
            brightBlue: '#79bbff',
            brightMagenta: '#e48fff',
            brightCyan: '#77d4ff',
            brightWhite: '#ffffff'
        }
    };
    
    // Initialize the terminal
    function setupTerminal() {
        // If using xterm.js, this would create the terminal instance
        // For now, we'll use a placeholder approach
        terminal.innerHTML = '';
        
        // Set terminal styles
        terminal.style.fontFamily = terminalSettings.fontFamily;
        terminal.style.fontSize = terminalSettings.fontSize + 'px';
        terminal.style.color = terminalSettings.theme.foreground;
        terminal.style.background = terminalSettings.theme.background;
        
        // Add welcome message
        terminal.innerHTML = '<div class="welcome-message">Connecting to SSH server...</div>';
    }
    
    // Connect to WebSocket
    function connectWebSocket() {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.close();
        }
        
        try {
            socket = new WebSocket(socketUrl);
            
            socket.onopen = function() {
                console.log("WebSocket connection established");
                isConnected = true;
                if (statusContainer) {
                    statusContainer.innerHTML = '<span class="status connected"></span> Connected';
                }
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
                terminal.innerHTML = '<div class="welcome-message">Connected! Starting terminal session...</div>';
            };
            
            socket.onmessage = function(event) {
                // Handle incoming messages from server
                const data = JSON.parse(event.data);
                
                if (data.error) {
                    displayError(data.error);
                    return;
                }
                
                if (data.data) {
                    // Append terminal data
                    appendToTerminal(data.data);
                }
                
                if (data.status === 'connected') {
                    terminal.innerHTML = '';
                }
            };
            
            socket.onclose = function(event) {
                isConnected = false;
                if (statusContainer) {
                    statusContainer.innerHTML = '<span class="status disconnected"></span> Disconnected';
                }
                
                let message = "Connection closed";
                if (event.reason) {
                    message += ": " + event.reason;
                }
                console.log(message);
                
                appendToTerminal("\r\n\r\n*** " + message + " ***\r\n\r\n");
            };
            
            socket.onerror = function(error) {
                console.error("WebSocket error:", error);
                displayError("WebSocket connection error");
            };
            
        } catch (error) {
            console.error("Failed to create WebSocket:", error);
            displayError("Failed to create WebSocket connection: " + error.message);
        }
    }
    
    // Send data to server
    function sendData(data) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                data: data
            }));
        } else {
            console.error("WebSocket is not connected");
            displayError("Terminal is not connected. Please try reconnecting.");
        }
    }
    
    // Handle key input
    function setupKeyHandlers() {
        document.addEventListener('keydown', function(event) {
            if (!isConnected) return;
            
            // Don't handle if user is typing in an input field that's not part of the terminal
            if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
                return;
            }
            
            // Control key combinations
            if (event.ctrlKey) {
                let key = String.fromCharCode(event.keyCode).toLowerCase();
                
                if (key === 'c' && !window.getSelection().toString()) {
                    // Ctrl+C (SIGINT)
                    sendData('\x03');
                    event.preventDefault();
                } else if (key === 'd') {
                    // Ctrl+D (EOF)
                    sendData('\x04');
                    event.preventDefault();
                } else if (key === 'z') {
                    // Ctrl+Z (SIGTSTP)
                    sendData('\x1A');
                    event.preventDefault();
                } else if (event.key === 'l') {
                    // Ctrl+L (clear screen)
                    terminal.innerHTML = '';
                    event.preventDefault();
                }
                return;
            }
            
            // Handle arrow keys, Enter, Tab, Backspace, etc.
            switch (event.key) {
                case 'ArrowUp':
                    sendData('\x1b[A');
                    break;
                case 'ArrowDown':
                    sendData('\x1b[B');
                    break;
                case 'ArrowRight':
                    sendData('\x1b[C');
                    break;
                case 'ArrowLeft':
                    sendData('\x1b[D');
                    break;
                case 'Enter':
                    sendData('\r');
                    break;
                case 'Tab':
                    sendData('\t');
                    break;
                case 'Backspace':
                    sendData('\x7f');
                    break;
                case 'Escape':
                    sendData('\x1b');
                    break;
                case 'Home':
                    sendData('\x1b[H');
                    break;
                case 'End':
                    sendData('\x1b[F');
                    break;
                case 'Delete':
                    sendData('\x1b[3~');
                    break;
                case 'PageUp':
                    sendData('\x1b[5~');
                    break;
                case 'PageDown':
                    sendData('\x1b[6~');
                    break;
                default:
                    // Regular character input
                    if (event.key.length === 1) {
                        sendData(event.key);
                    }
                    return;
            }
            
            event.preventDefault();
        });
    }
    
    // Append data to terminal
    function appendToTerminal(data) {
        const escapeHTML = (str) => {
            return str
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        };
        
        // Process ASCII color codes
        data = processAnsiCodes(escapeHTML(data));
        
        // Append to terminal with proper line breaks
        terminal.innerHTML += data.replace(/\r\n|\r|\n/g, '<br>');
        
        // Scroll to bottom
        terminal.scrollTop = terminal.scrollHeight;
    }
    
    // Process ANSI color codes
    function processAnsiCodes(text) {
        // This is a simplified version - in production you'd use a library like ansi-to-html
        // or implement full ANSI code handling
        const ansiColorMap = {
            '30': 'color: black;',
            '31': 'color: #ff6b6b;',
            '32': 'color: #56e356;',
            '33': 'color: #ffc107;',
            '34': 'color: #56a0e3;',
            '35': 'color: #d951ff;',
            '36': 'color: #4fc1ff;',
            '37': 'color: white;',
            '90': 'color: #656565;',
            '91': 'color: #ff8f8f;',
            '92': 'color: #72ff72;',
            '93': 'color: #ffd54f;',
            '94': 'color: #79bbff;',
            '95': 'color: #e48fff;',
            '96': 'color: #77d4ff;',
            '97': 'color: white;',
            '0': 'color: inherit;'
        };
        
        // Basic ANSI code replacement
        return text.replace(/\x1b\[(\d+)m/g, function(match, colorCode) {
            if (ansiColorMap[colorCode]) {
                return `<span style="${ansiColorMap[colorCode]}">`;
            }
            return '</span>';
        });
    }
    
    // Display error message
    function displayError(message) {
        terminal.innerHTML += `<div class="terminal-error">${message}</div>`;
        terminal.scrollTop = terminal.scrollHeight;
        
        if (loadingIndicator) {
            loadingIndicator.style.display = 'none';
        }
    }
    
    // Initialize the SSH client
    function init() {
        setupTerminal();
        connectWebSocket();
        setupKeyHandlers();
        
        // Handle window resize
        window.addEventListener('resize', function() {
            // If using a library like xterm.js, you'd need to call fit() here
            // For now, we don't need to do anything special
        });
        
        // Handle reconnection
        document.getElementById('reconnect-btn')?.addEventListener('click', function() {
            terminal.innerHTML = '<div class="welcome-message">Reconnecting...</div>';
            if (loadingIndicator) {
                loadingIndicator.style.display = 'flex';
            }
            connectWebSocket();
        });
        
        // Handle disconnect button
        document.getElementById('disconnect-btn')?.addEventListener('click', function() {
            if (socket) {
                socket.close();
            }
        });
    }
    
    // Start the client
    init();
}

// Initialize the client when the page loads
document.addEventListener('DOMContentLoaded', function() {
    const socketUrlElem = document.getElementById('websocket-url');
    if (socketUrlElem) {
        const socketUrl = socketUrlElem.getAttribute('data-url');
        if (socketUrl) {
            initWebSSHClient(socketUrl);
        } else {
            console.error("No WebSocket URL found in data-url attribute");
        }
    } else {
        console.error("Element with id 'websocket-url' not found");
    }
});