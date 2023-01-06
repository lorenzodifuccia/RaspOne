import re
import os
import logging
import telegram

from modules import RaspOneBaseModule
from src import config, UTILS_PATH, DEFAULT_NAME

module_logger = logging.getLogger(DEFAULT_NAME + ".module.vpn")


class ModuleVPN(RaspOneBaseModule):

    NAME = "vpn"
    DESCRIPTION = "Shows VPN info and get alerts on every VPN activity."

    USAGE = {
        "status": "Check if `openvpn` is running",
        "client": "Return the `.ovpn` profile file\n"
                  "_More_: `/vpn client <profile>`"
    }

    def __init__(self, core):
        super().__init__(core)

        self.profiles_path = config["Module - VPN"]["VPNProfilesPath"]
        self.regex_remote_host = re.compile(r"(?<=remote )[\w.]+")

    def alert(self, message):
        if not message or not len(message):
            return False

        module_logger.info("VPN Alert: %s" % message.encode("unicode_escape").decode("utf-8"))
        return self.core.send_message("🚨 VPN Alert 🚨:\n%s" % message)

    async def command(self, update, context):
        message = ""
        markdown = telegram.constants.ParseMode.MARKDOWN

        if context.args[0] == "status":
            status, error = self.core.server.is_process_running("openvpn")
            if error:
                message = error
                markdown = None

            else:
                message = "`openvpn` is %srunning %s" % \
                          ("" if status else "**not** ", "👍" if status else "👎")

        elif context.args[0] == "client":
            context.args.pop(0)

            try:
                profile_path = os.path.join(self.profiles_path, "UserOne.ovpn")
                if len(context.args):
                    profile_path = os.path.realpath(os.path.join(self.profiles_path, context.args.pop(0)))

                    if os.path.commonpath((self.profiles_path, profile_path)) != os.path.dirname(self.profiles_path):
                        raise OSError("invalid path: " + profile_path)

                with open(profile_path, "r") as profile_file:
                    profile_file_str = profile_file.read()
                    ip, err = self.core.modules["instances"]["ip"].get_ip_address()
                    if not err:
                        profile_file_str = self.regex_remote_host.sub(ip, profile_file_str)

                    await update.effective_message.reply_document(document=profile_file_str.encode(),
                                                                  filename=os.path.basename(profile_path))
                    return

            except OSError as os_error:
                message = "Error opening the client file: %s" % os_error
                markdown = None

        await update.effective_message.reply_text("VPN: " + message, parse_mode=markdown)

    @staticmethod
    def _build_utils():
        with open(os.path.join(UTILS_PATH, "rasp_vpn_alert.sh"), "w") as script:
            script.write(SCRIPT_TEMPLATE.replace("{{IPC_HOST}}", config["Server"]["IPCAddress"])
                         .replace("{{IPC_PORT}}", config["Server"]["IPCPort"]))

        module_logger.warning("** THIS MODULE REQUIRE YOUR ATTENTION, SEE LOGS AND utils/ DIRECTORY **")


SCRIPT_TEMPLATE = """#!/bin/bash

# OpenVPN Alert module
# 1. Copy the `utils/rasp_vpn_alert.sh` script into `/etc/openvpn/server/` directory.
# 2. `chmod +x /etc/openvpn/server/rasp_vpn_alert.sh`
# 3. Add the following lines into the `/etc/openvpn/server.conf`:
# ```
# script-security 2
# client-connect /etc/openvpn/server/rasp_vpn_alert.sh
# client-disconnect /etc/openvpn/server/rasp_vpn_alert.sh
# ```

message="New event '\`$script_type\`' on $(hostname).\\n"

if [ "$script_type" == "client-connect" ]; then
    message=$message"Date: $time_ascii\\n"
else
    message=$message"Date: $(date)\\nSession duration: $time_duration sec.\\n"
    message=$message"Traffic (in \`bytes\`): $bytes_received recv, $bytes_sent sent\\n"
fi

message=$message"Common Name: *$common_name*\\n"

if [ ! -z "$trusted_ip" ]; then
    message=$message"Trusted IP: '\`$trusted_ip\`'\\n"
fi

if [ ! -z "$untrusted_ip" ]; then
    message=$message"*Untrusted IP*: '\`$untrusted_ip\`'\\n"
fi

if [ ! -z "$ifconfig_pool_local_ip" ]; then
    message=$message"Pool local IP: $ifconfig_pool_local_ip\\n"
fi

if [ ! -z "$ifconfig_pool_remote_ip" ]; then
    message=$message"Pool remote IP: $ifconfig_pool_remote_ip\\n"
fi

echo '{"service": "vpn", "message": "'$message'"}' | nc {{IPC_HOST}} {{IPC_PORT}}
"""
