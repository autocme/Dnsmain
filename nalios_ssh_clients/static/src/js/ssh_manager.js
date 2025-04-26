
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { isMacOS } from "@web/core/browser/feature_detection";
import { Component, useRef, onMounted, onWillUnmount } from "@odoo/owl";

const ALPHANUM_KEYS = "abcdefghijklmnopqrstuvwxyz0123456789".split("");
const NAV_KEYS = [
    "arrowleft", "arrowright", "arrowup", "arrowdown", "pageup", "pagedown",
    "home", "end", "backspace", "enter", "tab", "delete",
];
const MODIFIERS = new Set(["alt", "control", "shift"]);
const AUTHORIZED_KEYS = new Set([...ALPHANUM_KEYS, ...NAV_KEYS, "escape"]);

export class SshManager extends Component {
    setup() {
        this.client_id = this.props.action.context.active_id;
        this.orm = useService('orm');
        this.cmdline = useRef('cmdline');
        this.terminal = useRef('terminal');
        this.clientName = useRef('clientName');
        this.callClient();
        onMounted(() => {
            window.setTimeout(() => {
                this.cmdline.el.focus();
            }, 0);
            this.colorize();
        });
        onWillUnmount(() => {
            this.disconnectClient();
        });
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

    async inputKeydownSendCommand(ev) {
        const hotkey = this.getActiveHotkey(ev);
        if (hotkey === "enter") {
            const value = this.cmdline.el.value;
            const lastPre = document.querySelector('pre:last-child');
            if (lastPre) {
                lastPre.innerHTML = lastPre.innerHTML.replace(/\n$/, '') + '\n' + value + '\n';
            } else {
                document.querySelector('#terminal_window').innerHTML += value + '\n';
            }
            this.cmdline.el.value = '';
            await this._sendCommand(value).then(() => {
                this.terminal.el.scrollTo(0, this.terminal.el.scrollHeight);
            });
        }
    }

    async sendCmd(ev) {
        if (ev && ev.target) {
            // This is called from the button click
            const cmd = this.cmdline.el.value;
            if (cmd) {
                const lastPre = document.querySelector('pre:last-child');
                if (lastPre) {
                    lastPre.innerHTML = lastPre.innerHTML.replace(/\n$/, '') + '\n' + cmd + '\n';
                } else {
                    document.querySelector('#terminal_window').innerHTML += cmd + '\n';
                }
                this.cmdline.el.value = '';
                await this._sendCommand(cmd).then(() => {
                    this.terminal.el.scrollTo(0, this.terminal.el.scrollHeight);
                });
            }
        } else {
            // This is the internal method call with the command
            await this._sendCommand(ev);
        }
    }
    
    async _sendCommand(cmd) {
        const res = await this.orm.call('ssh.client', 'exec_command', [[this.client_id], cmd]);
        this.terminal.el.innerHTML += res;
    }

    async callClient() {
        const res1 = await this.orm.call('ssh.client', 'get_client_name', [this.client_id]);
        this.clientName.el.innerText = res1;
        const res = await this.orm.call('ssh.client', 'get_ssh_connection', [this.client_id]);
        this.terminal.el.innerHTML += res;
    }

    async exit(ev) {
        await this.disconnectClient();
        history.back();
    }

    async disconnectClient() {
        await this.orm.call('ssh.client', 'disconnect_client', [this.client_id]);
    }

    async colorize() {
        const colors = await this.orm.call('ssh.client', 'get_colors', [this.client_id]);
        this.terminal.el.style.setProperty('background-color', colors.background, 'important');
        this.terminal.el.style.setProperty('color', colors.text, 'important');
    }
}

// In OWL 2.0, we set the template directly in the component definition
SshManager.props = {
    action: { type: Object }
};
SshManager.template = 'nalios_ssh_clients.ssh_manager';

// Register the component as a client action
registry.category('actions').add('ssh_client_main_window', SshManager);
