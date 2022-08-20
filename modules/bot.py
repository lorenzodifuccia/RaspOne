import logging

from src import DEFAULT_NAME
from modules import RaspOneBaseModule

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

    def command(self, update, context):
        if context.args[0] == "restart":
            update.effective_message.reply_text("Restarting... 🤞")
            self.core.restart()

        elif context.args[0] == "debug":
            context.args.pop(0)
            if len(context.args):
                try:
                    request_id = int(context.args[0])
                    update.effective_message.reply_text(
                        self.network.get_error(request_id) + "\n" +
                        self.network.get_request_details(request_id)
                    )
                except ValueError:
                    pass
