import os
import logging
import telegram

from modules import RaspOneBaseModule
from src import config, DEFAULT_NAME, UTILS_PATH

module_logger = logging.getLogger(DEFAULT_NAME + ".module.ssh")


class ModuleSSH(RaspOneBaseModule):

    NAME = "ssh"
    DESCRIPTION = "Shows SSH info and get alerts on every SSH activity."

    USAGE = {
        "status": "Check if `sshd` is running",
        "port": "Show listening port",
        "fingerprint": "return ECDSA and ED25519 keys fingerprints for verification"
    }

    def __init__(self, core):
        super().__init__(core)

        self.ssh_port = config["Module - SSH"]["SSHPort"]

    def alert(self, message):
        if not message or not len(message):
            return False

        module_logger.info("SSH Alert: %s" % message.encode("unicode_escape").decode("utf-8"))
        return self.core.send_message("🚨 SSH Alert 🚨:\n%s" % message)

    async def command(self, update, context):
        message = ""
        markdown = telegram.constants.ParseMode.MARKDOWN

        if context.args[0] == "status":
            status, error = self.core.server.is_process_running("sshd")
            if error:
                message = error
                markdown = None

            else:
                message = "`sshd` is %srunning %s" % \
                          ("" if status else "**not** ", "👍" if status else "👎")

        elif context.args[0] == "port":
            if self.ssh_port:
                message = "🚪 " + self.ssh_port

            else:
                ssh_port, error = self._grep_ssh_port()
                if error:
                    message = error
                    markdown = None

                else:
                    message = "🚪 " + ssh_port

        elif context.args[0] == "fingerprint":
            ecdsa_fingerprint, error = self.get_ssh_fingerprint()
            if error:
                message = error
                markdown = None

            else:
                message = "ECDSA: `%s`" % ecdsa_fingerprint

            ed25519_fingerprint, error = self.get_ssh_fingerprint(ed25519=True)
            if error:
                message += "\n" + error
                markdown = None

            else:
                message += "\nED25519: `%s`" % ed25519_fingerprint

        await update.effective_message.reply_text("SSH:\n" + message, parse_mode=markdown)

    def _grep_ssh_port(self):
        proc, stdout, stderr = self.core.server.run(("grep", '"Port "', "/etc/ssh/sshd_config"))
        if not proc:
            return False, self.core.server.default_error_message

        elif len(stderr):
            return False, stderr

        elif len(stdout):
            config_ports = list(filter(lambda c: len(c) and not c.startswith("#"), stdout.split("\n")))
            if not len(config_ports):
                return "22", None

            elif len(config_ports) == 1:
                return config_ports[0], None

            else:
                return "Multiple port specified in `/etc/ssh/sshd_config` in the following order:\n" + \
                       "\n".join(config_ports), None

        else:
            return False, "Error: `Port` not found in `/etc/ssh/sshd_config`."

    def get_ssh_fingerprint(self, ed25519=False):
        proc, stdout, stderr = self.core.server.run(("ssh-keygen", "-lf", "/etc/ssh/ssh_host_%s_key.pub" %
                                                     ("ed25519" if ed25519 else "ecdsa")))
        if not proc:
            return False, self.core.server.default_error_message

        elif len(stderr):
            return False, stderr

        elif len(stdout):
            try:
                fingerprint = stdout.split(" ")[1]

            except IndexError:
                fingerprint = stdout

            return fingerprint, None

        else:
            return False, self.core.server.default_error_message

    @staticmethod
    def _build_utils():
        with open(os.path.join(UTILS_PATH, "rasp_ssh_alert.sh"), "w") as script:
            script.write(SCRIPT_TEMPLATE.replace("{{IPC_HOST}}", config["Server"]["IPCAddress"])
                                        .replace("{{IPC_PORT}}", config["Server"]["IPCPort"]))

    module_logger.warning("** THIS MODULE REQUIRE YOUR ATTENTION, SEE LOGS AND utils/ DIRECTORY **")


SCRIPT_TEMPLATE = """#!/bin/bash

# SSH Alert module
# 1. `chmod +x utils/rasp_ssh_alert.sh`
# 2. Add `session optional pam_exec.so seteuid /path/to/RaspOne/utils/rasp_ssh_alert.sh` 
#    into `/etc/pam.d/sshd`

message="New event '\`$PAM_TYPE\`' on $(hostname).\\nDate: $(date)\\n*From*: '\`$PAM_RHOST\`'"

if [ ! -z "$PAM_RUSER" ]; then
    message=$message", $PAM_RUSER"
fi

message=$message"\\nUser: $PAM_USER (TTY: $PAM_TTY)"

echo '{"service": "ssh", "message": "'$message'"}' | nc {{IPC_HOST}} {{IPC_PORT}}
"""
