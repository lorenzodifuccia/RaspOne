import os
import telegram
import logging

from src import DEFAULT_NAME, UTILS_PATH
from modules import RaspOneBaseModule

module_logger = logging.getLogger(DEFAULT_NAME + ".module.system")


class ModuleSystem(RaspOneBaseModule):

    NAME = "system"
    DESCRIPTION = "Manage the system"

    USAGE = {
        "reboot": "Reboot the system"
    }

    def __init__(self, core):
        super().__init__(core)

        self.reboot_keyboard = [[telegram.InlineKeyboardButton("Yes!", callback_data="SYSTEM_REBOOT_True"),
                                 telegram.InlineKeyboardButton("No...", callback_data="SYSTEM_REBOOT_False")]]

    def command(self, update, context):
        if context.args[0] == "reboot":
            update.effective_message.reply_text("Are you sure? 😨😨",
                                                reply_markup=telegram.InlineKeyboardMarkup(self.reboot_keyboard))

            self.register_query_callback("REBOOT", self.query_handler_reboot)

    def query_handler_reboot(self, update, _):
        query = update.callback_query
        if query.data == "True":
            query.edit_message_text(text="😊👋 See Ya!!")

            _, reboot_err = self.reboot()
            if reboot_err:
                query.edit_message_text(text=reboot_err)

        else:
            query.edit_message_text(text="😅")

        self.remove_callback("REBOOT")

    def reboot(self):
        module_logger.warning("Rebooting...")
        proc, stdout, stderr = self.core.server.run(
            "sudo /bin/systemctl reboot",
            shell=True
        )
        if not proc:
            return False, self.core.server.default_error_message

        elif len(stderr):
            return False, stderr

        elif len(stdout):
            return False, stdout

        else:
            return True, None

    @staticmethod
    def _build_utils():
        with open(os.path.join(UTILS_PATH, "rasp_one_system.conf"), "w") as script:
            script.write(SCRIPT_TEMPLATE)

    module_logger.warning("** THIS MODULE REQUIRE YOUR ATTENTION, SEE LOGS AND utils/ DIRECTORY **")


SCRIPT_TEMPLATE = """# System module
# sudo copy this file into `/etc/sudoers.d/`

pi    ALL=NOPASSWD:    /bin/systemctl restart
"""
