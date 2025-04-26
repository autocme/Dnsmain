
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
        this.savedCommandsPanel = useRef('savedCommandsPanel');
        
        // State for reactive UI
        this.state = useState({
            commandHistory: [],
            historyIndex: -1,
            isConnected: false,
            isFullscreen: false,
            currentCommand: '',
            showHistory: false,
            showSavedCommands: false,
            savedCommands: [],
            currentCategory: 'all'
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
            // Wrap the response in a div for styling
            this.terminal.el.innerHTML += `<div class="terminal-response">${res}</div>`;
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
            
            // Load common commands for this server type for auto-completion
            await this.loadCommonCommands();
            
            // Add welcome message and connection info with enhanced styling
            this.terminal.el.innerHTML = `<div class="terminal-output">
                <div class="terminal-welcome">
                    <strong>🔐 SSH connection established to ${clientName}</strong>
                    <div class="welcome-details">
                        <p>Type commands below and press Enter to execute</p>
                        <ul class="terminal-tips">
                            <li>Use <kbd>Tab</kbd> for command completion</li>
                            <li>Press <kbd>↑</kbd>/<kbd>↓</kbd> to navigate command history</li>
                            <li>Type <code>help</code> to see common commands</li>
                        </ul>
                    </div>
                </div>
            </div>`;
            
            // Add the actual connection output
            this.terminal.el.innerHTML += `<div class="terminal-response">${connectionOutput}</div>`;
            
            // Initialize auto-completion
            this.setupAutoCompletion();
            
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
    
    async loadCommonCommands() {
        // Common Unix/Linux commands for auto-completion
        this.state.commonCommands = [
            // File operations
            'ls', 'cd', 'pwd', 'mkdir', 'touch', 'rm', 'cp', 'mv', 'cat', 'less', 'head', 'tail',
            // System info
            'uname', 'whoami', 'ps', 'top', 'htop', 'free', 'df', 'du', 'ifconfig', 'ip',
            // Text processing
            'grep', 'sed', 'awk', 'sort', 'uniq', 'wc', 'cut',
            // Network
            'ping', 'ssh', 'scp', 'curl', 'wget', 'netstat', 'traceroute', 'nslookup', 'dig',
            // Package management
            'apt', 'apt-get', 'yum', 'dnf', 'pacman', 'snap', 'dpkg',
            // Process management
            'kill', 'pkill', 'killall', 'nohup', 'bg', 'fg', 'jobs', 'screen', 'tmux',
            // AWS specific
            'aws', 'eb', 's3cmd', 'aws-shell',
            // Docker
            'docker', 'docker-compose', 'podman',
            // Git
            'git', 'gh',
            // Common user commands
            'sudo', 'su', 'passwd', 'who', 'w', 'last', 'id',
            // Help
            'man', 'info', 'help',
            // Compression 
            'tar', 'gzip', 'zip', 'unzip', 'bzip2',
            // Shell
            'echo', 'export', 'env', 'history',
        ];
        
        // Common command suffixes/options
        this.state.commonOptions = [
            '-a', '-l', '-h', '--help', '-v', '--version',
            '-r', '-f', '-d', '-p', '-i', '-o', '-n', '-s',
            '-u', '-g', '-m', '-t', '-c', '-x', '-z', '-b',
        ];
        
        // Try to get recent commands for this specific server
        try {
            const recentCommands = await this.orm.call(
                'ssh.saved.command',
                'search_read',
                [
                    [['ssh_client_id', '=', this.client_id]],
                    ['command']
                ],
                { limit: 20, order: 'last_used DESC' }
            );
            
            // Add these commands to our common commands list for auto-completion
            if (recentCommands && recentCommands.length) {
                recentCommands.forEach(cmd => {
                    const baseCommand = cmd.command.split(' ')[0];
                    if (baseCommand && !this.state.commonCommands.includes(baseCommand)) {
                        this.state.commonCommands.push(baseCommand);
                    }
                });
            }
        } catch (error) {
            console.error("Failed to load recent commands:", error);
        }
    }
    
    setupAutoCompletion() {
        this.cmdline.el.addEventListener('keydown', (event) => {
            // Tab key for auto-completion
            if (event.key === 'Tab') {
                event.preventDefault();
                this.handleTabCompletion();
            }
        });
    }
    
    handleTabCompletion() {
        const currentInput = this.cmdline.el.value.trim();
        
        if (!currentInput) return;
        
        const lastWord = currentInput.split(' ').pop();
        const prefix = currentInput.substring(0, currentInput.length - lastWord.length);
        
        // Find matching commands
        let matches = [];
        
        if (currentInput.includes(' ')) {
            // We're completing an option or argument
            matches = this.state.commonOptions.filter(opt => 
                opt.startsWith(lastWord)
            );
        } else {
            // We're completing a command
            matches = this.state.commonCommands.filter(cmd => 
                cmd.startsWith(lastWord)
            );
        }
        
        if (matches.length === 1) {
            // One match - complete it
            this.cmdline.el.value = prefix + matches[0] + ' ';
        } else if (matches.length > 1) {
            // Multiple matches - show options
            const commonPrefix = this.findCommonPrefix(matches);
            
            if (commonPrefix.length > lastWord.length) {
                // We can complete partially
                this.cmdline.el.value = prefix + commonPrefix;
            } else {
                // Show all options
                const matchesHtml = matches.map(m => `<span class="completion-option">${m}</span>`).join(' ');
                this.terminal.el.innerHTML += `
                    <div class="terminal-output completion-suggestions">
                        <div class="completion-header">Tab completion options:</div>
                        <div class="completion-list">${matchesHtml}</div>
                    </div>
                `;
                this.terminal.el.scrollTo(0, this.terminal.el.scrollHeight);
            }
        }
    }
    
    findCommonPrefix(strings) {
        if (!strings.length) return '';
        
        const firstStr = strings[0];
        let prefix = '';
        
        for (let i = 0; i < firstStr.length; i++) {
            const char = firstStr[i];
            if (strings.every(str => str[i] === char)) {
                prefix += char;
            } else {
                break;
            }
        }
        
        return prefix;
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
        if (this.state.showSavedCommands) {
            this.toggleSavedCommands(); // Close saved commands panel if open
        }
        
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
    
    // Saved Commands functionality
    
    async toggleSavedCommands() {
        if (this.state.showHistory) {
            this.toggleCommandHistory(); // Close history panel if open
        }
        
        this.state.showSavedCommands = !this.state.showSavedCommands;
        const savedCommandsPanel = this.savedCommandsPanel?.el;
        
        if (this.state.showSavedCommands) {
            if (savedCommandsPanel) {
                savedCommandsPanel.classList.add('visible');
            }
            
            // Load saved commands if needed
            if (!this.state.savedCommands.length) {
                await this.loadSavedCommands();
            }
            
        } else if (savedCommandsPanel) {
            savedCommandsPanel.classList.remove('visible');
        }
    }
    
    async loadSavedCommands() {
        try {
            const commands = await this.orm.call(
                'ssh.saved.command', 
                'search_read', 
                [
                    [['ssh_client_id', '=', this.client_id]],
                    ['id', 'name', 'command', 'description', 'category', 'is_favorite', 'use_count', 'last_used']
                ],
                { order: 'name' }
            );
            
            this.state.savedCommands = commands || [];
        } catch (error) {
            console.error('Error loading saved commands:', error);
            this.notification.add("Failed to load saved commands", {
                type: 'warning',
            });
        }
    }
    
    async useSavedCommand(cmd) {
        // Set the command to the input field
        this.cmdline.el.value = cmd.command;
        
        // Toggle the panel
        this.toggleSavedCommands();
        
        // Focus the command line
        this.cmdline.el.focus();
        
        // Update usage statistics
        try {
            await this.orm.call('ssh.saved.command', 'execute_command', [cmd.id]);
            
            // Update local state
            const index = this.state.savedCommands.findIndex(c => c.id === cmd.id);
            if (index !== -1) {
                this.state.savedCommands[index].use_count += 1;
                this.state.savedCommands[index].last_used = new Date().toISOString();
            }
        } catch (error) {
            console.error('Error updating saved command usage:', error);
        }
    }
    
    async createSavedCommand(ev) {
        ev.stopPropagation();
        
        // Get current command if any
        const currentCommand = this.cmdline.el.value.trim();
        
        const action = {
            type: 'ir.actions.act_window',
            res_model: 'ssh.saved.command',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_ssh_client_id: this.client_id,
                default_command: currentCommand,
            },
        };
        
        const result = await this.orm.call(
            'ir.actions.act_window',
            'read',
            [action.id || false],
            { context: action.context }
        );
        
        // After creating, reload saved commands
        await this.loadSavedCommands();
    }
    
    async editSavedCommand(ev, cmd) {
        ev.stopPropagation();
        
        const action = {
            type: 'ir.actions.act_window',
            res_model: 'ssh.saved.command',
            res_id: cmd.id,
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
        };
        
        const result = await this.orm.call(
            'ir.actions.act_window',
            'read',
            [action.id || false]
        );
        
        // After editing, reload saved commands
        await this.loadSavedCommands();
    }
    
    async deleteSavedCommand(ev, cmd) {
        ev.stopPropagation();
        
        // Confirm deletion
        if (!confirm(`Are you sure you want to delete the saved command "${cmd.name}"?`)) {
            return;
        }
        
        try {
            await this.orm.unlink('ssh.saved.command', [cmd.id]);
            
            // Update local state
            this.state.savedCommands = this.state.savedCommands.filter(c => c.id !== cmd.id);
            
            this.notification.add(`Command "${cmd.name}" deleted`, {
                type: 'info',
            });
        } catch (error) {
            console.error('Error deleting saved command:', error);
            this.notification.add("Failed to delete command", {
                type: 'warning',
            });
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
