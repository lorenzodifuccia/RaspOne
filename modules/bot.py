import os
import logging

from modules import RaspOneBaseModule
from src import config, DEFAULT_NAME, UTILS_PATH

module_logger = logging.getLogger(DEFAULT_NAME + ".module.bot")


class ModuleBot(RaspOneBaseModule):
    NAME = "bot"
    DESCRIPTION = "Control the RaspOne instance"

    USAGE = {
        "restart": "Restart the bot (loads new modules)",
        "request": "Retrieve details about a failed `network` request"
    }

    def __init__(self, core):
        super().__init__(core)

    async def command(self, update, context):
        if context.args[0] == "restart":
            await update.effective_message.reply_text("Restarting... 🤞")
            self.core.restart()
            return

        elif context.args[0] == "request":
            context.args.pop(0)
            if not len(context.args):
                await update.effective_message.reply_text("Error: expecting a request ID!")
                return

            try:
                request_id = int(context.args[0])
                await update.effective_message.reply_text(
                    self.network.get_error(request_id) + "\n" +
                    self.network.get_request_details(request_id)
                )
            except ValueError:
                pass

    @staticmethod
    def _build_utils():
        script_template = \
         """#!/bin/bash

# Heartbeat CRON Check
# sudo crontab -e
# */60 * * * * /full/path/to/cron_check.sh

STATUS=$(echo '{"service": "_heartbeat_"}' | nc {{IPC_HOST}} {{IPC_PORT}})
if [[ "$STATUS" != "ok" ]]; then
        service rasp-one stop
        service rasp-one start
fi
"""
        with open(os.path.join(UTILS_PATH, "rasp_cron_check.sh"), "w") as script:
            script.write(script_template.replace("{{IPC_HOST}}", config["Server"]["IPCAddress"])
                         .replace("{{IPC_PORT}}", config["Server"]["IPCPort"]))

        module_logger.warning("** THIS MODULE REQUIRE YOUR ATTENTION, SEE LOGS AND utils/ DIRECTORY **")
