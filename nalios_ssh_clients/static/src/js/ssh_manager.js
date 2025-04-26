
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { isMacOS } from "@web/core/browser/feature_detection";
import { Component, useRef, useState, onMounted, onWillUnmount } from "@odoo/owl";

const ALPHANUM_KEYS = "abcdefghijklmnopqrstuvwxyz0123456789".split("");
const NAV_KEYS = [
    "arrowleft", "arrowright", "arrowup", "arrowdown", "pageup", "pagedown",
    "home", "end", "backspace", "enter", "tab", "delete", "escape"
];
const SPECIAL_KEYS = ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "-", "_", "+", "=", "[", "]", "{", "}", ";", ":", "'", "\"", ",", ".", "/", "?", "|", "\\", "`", "~"];
const MODIFIERS = new Set(["alt", "control", "shift"]);
const AUTHORIZED_KEYS = new Set([...ALPHANUM_KEYS, ...NAV_KEYS, ...SPECIAL_KEYS, " "]);

export class SshManager extends Component {
    setup() {
        this.client_id = this.props.action.context.active_id;
        this.orm = useService('orm');
        this.notification = useService('notification');
        
        // Refs for DOM elements
        this.cmdline = useRef('cmdline');
        this.terminal = useRef('terminal');
        this.clientName = useRef('clientName');
        this.connectionStatus = useRef('connectionStatus');
        this.hostInfo = useRef('hostInfo');
        this.historyPanel = useRef('historyPanel');
        
        // State for reactive UI
        this.state = useState({
            commandHistory: [],
            historyIndex: -1,
            isConnected: false,
            isFullscreen: false,
            currentCommand: '',
            showHistory: false
        });
        
        this.MAX_HISTORY = 50; // Maximum items in command history
        
        // Initialize connection
        this.initConnection();
        
        onMounted(() => {
            window.setTimeout(() => {
                this.cmdline.el.focus();
            }, 100);
            this.colorize();
            
            // Handle Ctrl/Cmd+C for copying
            document.addEventListener('keydown', this.handleGlobalKeypress.bind(this));
            
            // Set host info
            this.getConnectionInfo();
        });
        
        onWillUnmount(() => {
            this.disconnectClient();
            document.removeEventListener('keydown', this.handleGlobalKeypress.bind(this));
        });
    }
    
    async getConnectionInfo() {
        try {
            const info = await this.orm.call('ssh.client', 'get_connection_details', [this.client_id]);
            if (info) {
                this.hostInfo.el.innerText = `${info.user}@${info.host}:${info.port}`;
            }
        } catch (error) {
            console.error("Failed to get connection info:", error);
        }
    }
    
    handleGlobalKeypress(event) {
        // Handle Ctrl+C globally for copy
        if ((event.ctrlKey || event.metaKey) && event.key === 'c') {
            const selection = window.getSelection().toString();
            if (selection && this.terminal.el.contains(window.getSelection().anchorNode)) {
                // Let the default copy action occur if text is selected in the terminal
                return;
            }
        }
        
        // Handle Escape key to hide history panel
        if (event.key === 'Escape' && this.state.showHistory) {
            this.toggleCommandHistory();
            event.preventDefault();
        }
        
        // Handle Ctrl+L to clear terminal
        if ((event.ctrlKey || event.metaKey) && event.key === 'l') {
            this.clearTerminal();
            event.preventDefault();
        }
    }

    getActiveHotkey(ev) {
        const hotkey = [];
        if (isMacOS() ? ev.ctrlKey : ev.altKey) hotkey.push("alt");
        if (isMacOS() ? ev.metaKey : ev.ctrlKey) hotkey.push("control");
        if (ev.shiftKey) hotkey.push("shift");
        let key = ev.key.toLowerCase();
        if (ev.code && ev.code.startsWith("Digit")) key = ev.code.slice(-1);
        if (!AUTHORIZED_KEYS.has(key) && ev.code && ev.code.startsWith("Key")) key = ev.code.slice(-1).toLowerCase();
        if (!MODIFIERS.has(key)) hotkey.push(key);
        return hotkey.join("+");
    }

    async handleCommandInput(ev) {
        const hotkey = this.getActiveHotkey(ev);
        
        // Command submission with Enter
        if (hotkey === "enter") {
            const value = this.cmdline.el.value.trim();
            if (value) {
                this.executeCommand(value);
            }
            return;
        }
        
        // Command history navigation with arrow keys
        if (hotkey === "arrowup") {
            this.navigateHistory(-1);
            ev.preventDefault();
        } else if (hotkey === "arrowdown") {
            this.navigateHistory(1);
            ev.preventDefault();
        }
        
        // Clear terminal with Ctrl+L
        if (hotkey === "control+l") {
            this.clearTerminal();
            ev.preventDefault();
        }
        
        // Cancel command with Escape
        if (hotkey === "escape") {
            this.cmdline.el.value = '';
            this.state.historyIndex = -1;
            ev.preventDefault();
        }
    }
    
    navigateHistory(direction) {
        const history = this.state.commandHistory;
        if (!history.length) return;
        
        // If we're not already navigating, store the current command
        if (this.state.historyIndex === -1) {
            this.state.currentCommand = this.cmdline.el.value;
        }
        
        let newIndex = this.state.historyIndex + direction;
        
        // Constrain index to valid range
        if (newIndex >= history.length) {
            // Past the end of history - restore current command
            this.cmdline.el.value = this.state.currentCommand;
            this.state.historyIndex = -1;
            return;
        } else if (newIndex < 0) {
            newIndex = 0;
        }
        
        this.state.historyIndex = newIndex;
        this.cmdline.el.value = history[newIndex];
        
        // Move cursor to end of input
        window.setTimeout(() => {
            this.cmdline.el.selectionStart = this.cmdline.el.selectionEnd = this.cmdline.el.value.length;
        }, 0);
    }

    async executeCommand(command) {
        // Format command with a prompt symbol before adding to terminal
        const commandWithPrompt = `<div class="terminal-output">
            <span class="terminal-command">$ ${command}</span>
        </div>`;
        
        // Add to terminal display
        this.terminal.el.innerHTML += commandWithPrompt;
        
        // Add to command history if not duplicate of last command
        if (!this.state.commandHistory.length || 
            this.state.commandHistory[0] !== command) {
            this.state.commandHistory.unshift(command);
            
            // Limit history size
            if (this.state.commandHistory.length > this.MAX_HISTORY) {
                this.state.commandHistory.pop();
            }
        }
        
        // Reset history navigation
        this.state.historyIndex = -1;
        
        // Clear input field
        this.cmdline.el.value = '';
        
        // Send command to server
        try {
            await this._sendCommand(command);
        } catch (error) {
            this.terminal.el.innerHTML += `<div class="terminal-output error">Error executing command: ${error.message || 'Unknown error'}</div>`;
        }
        
        // Scroll to bottom
        this.terminal.el.scrollTo(0, this.terminal.el.scrollHeight);
    }

    async sendCmd(ev) {
        const command = this.cmdline.el.value.trim();
        if (command) {
            await this.executeCommand(command);
        }
    }
    
    async _sendCommand(cmd) {
        try {
            const res = await this.orm.call('ssh.client', 'exec_command', [[this.client_id], cmd]);
            
            // Process the response to ensure proper wrapping of long lines
            let processedResponse = res;
            
            // If the response contains ANSI content, make sure it's properly wrapped
            if (res.includes('ansi2html-content')) {
                // The response already contains HTML with ANSI formatting
                // Add classes to ensure proper wrapping
                processedResponse = res.replace(
                    /<pre class="ansi2html-content">/g, 
                    '<pre class="ansi2html-content terminal-formatted">'
                );
            }
            
            // Wrap the response in a div for styling
            this.terminal.el.innerHTML += `<div class="terminal-response">${processedResponse}</div>`;
        } catch (error) {
            console.error("Command execution error:", error);
            throw error;
        }
    }

    async initConnection() {
        try {
            // Get client name
            const clientName = await this.orm.call('ssh.client', 'get_client_name', [this.client_id]);
            this.clientName.el.innerText = clientName;
            
            // Establish SSH connection
            const connectionOutput = await this.orm.call('ssh.client', 'get_ssh_connection', [this.client_id]);
            
            // Add welcome message and connection info
            this.terminal.el.innerHTML = `<div class="terminal-output">
                <div class="terminal-welcome">
                    <strong>🔐 SSH connection established to ${clientName}</strong>
                    <br/>Type commands below and press Enter to execute
                </div>
            </div>`;
            
            // Add the actual connection output
            this.terminal.el.innerHTML += `<div class="terminal-response">${connectionOutput}</div>`;
            
            // Update connection status
            this.state.isConnected = true;
        } catch (error) {
            console.error("Connection error:", error);
            this.terminal.el.innerHTML = `<div class="terminal-output error">
                Connection failed: ${error.message || 'Unknown error'}
            </div>`;
            this.connectionStatus.el.innerText = "Disconnected";
            this.connectionStatus.el.previousElementSibling.classList.remove('connected');
            this.connectionStatus.el.previousElementSibling.classList.add('disconnected');
            this.state.isConnected = false;
        }
    }

    async exit(ev) {
        await this.disconnectClient();
        history.back();
    }

    async disconnectClient() {
        if (this.state.isConnected) {
            try {
                await this.orm.call('ssh.client', 'disconnect_client', [this.client_id]);
                this.state.isConnected = false;
            } catch (error) {
                console.error("Error disconnecting:", error);
            }
        }
    }

    async colorize() {
        try {
            const colors = await this.orm.call('ssh.client', 'get_colors', [this.client_id]);
            this.terminal.el.style.setProperty('background-color', colors.background, 'important');
            this.terminal.el.style.setProperty('color', colors.text, 'important');
        } catch (error) {
            console.error("Error setting terminal colors:", error);
        }
    }
    
    // New UI actions
    
    clearTerminal() {
        this.terminal.el.innerHTML = '';
        this.cmdline.el.focus();
    }
    
    toggleCommandHistory() {
        this.state.showHistory = !this.state.showHistory;
        if (this.state.showHistory) {
            this.historyPanel.el.classList.add('visible');
        } else {
            this.historyPanel.el.classList.remove('visible');
        }
    }
    
    useHistoryCommand(command) {
        this.cmdline.el.value = command;
        this.toggleCommandHistory();
        this.cmdline.el.focus();
    }
    
    copyToClipboard() {
        const text = this.terminal.el.innerText;
        navigator.clipboard.writeText(text).then(() => {
            this.notification.add("Terminal content copied to clipboard", {
                type: 'info',
            });
        }).catch(err => {
            console.error('Failed to copy: ', err);
            this.notification.add("Failed to copy to clipboard", {
                type: 'warning',
            });
        });
    }
    
    toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                console.error(`Error attempting to enable fullscreen: ${err.message}`);
            });
            this.state.isFullscreen = true;
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
                this.state.isFullscreen = false;
            }
        }
    }
}

// In OWL 2.0, we set the template directly in the component definition
SshManager.props = {
    action: { type: Object }
};
SshManager.template = 'nalios_ssh_clients.ssh_manager';

// Register the component as a client action
registry.category('actions').add('ssh_client_main_window', SshManager);
