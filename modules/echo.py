import os
import logging

from modules import RaspOneBaseModule
from src import config, DEFAULT_NAME, UTILS_PATH

module_logger = logging.getLogger(DEFAULT_NAME + ".module.echo")


class ModuleEcho(RaspOneBaseModule):
    NAME = "echo"
    DESCRIPTION = "Echo messages from server"

    USAGE = DESCRIPTION

    def __init__(self, core):
        super().__init__(core)

    def alert(self, message):
        if not message or not len(message):
            return False

        return self.core.send_message(message, markdown=True)

    @staticmethod
    def _build_utils():
        script_template = \
         """#!/bin/bash
echo '{"service": "echo", "message": "Echo Test!"}' | nc {{IPC_HOST}} {{IPC_PORT}}
"""
        with open(os.path.join(UTILS_PATH, "rasp_echo_alert.sh"), "w") as script:
            script.write(script_template.replace("{{IPC_HOST}}", config["Server"]["IPCAddress"])
                         .replace("{{IPC_PORT}}", config["Server"]["IPCPort"]))

        module_logger.warning("** THIS MODULE REQUIRE YOUR ATTENTION, SEE LOGS AND utils/ DIRECTORY **")
