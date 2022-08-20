import telegram.ext

from src import network


# Base Module
class RaspOneBaseModule:

    NAME = "BaseModule"
    DESCRIPTION = "Base module description."

    # USAGE can be dict or str
    USAGE = {
        "method": "Method description"
    }

    def __init__(self, core, *args, **kwargs):
        self.core = core

        self.network = network.Network(self.NAME)
        self.core.ipc.add_service(self.NAME, self.alert)

        self._build_utils()

    # Command
    def command(self, update: telegram.Update, context: telegram.ext.CallbackContext):
        pass

    # Alert
    def alert(self, message: str):
        pass

    # Callbacks
    def register_query_callback(self, tag, callback):
        self.core.register_query_callback(f"{self.NAME.upper()}_{tag}", callback)

    def register_message_callback(self, tag, callback, message_filter=None):
        self.core.register_message_callback(f"{self.NAME.upper()}_{tag}", callback, message_filter)

    def remove_callback(self, tag):
        self.core.remove_callback(f"{self.NAME.upper()}_{tag}")

    # Default Handler - Used by core.py
    def default_handler(self, update: telegram.Update, context: telegram.ext.CallbackContext):
        self.core.remove_callbacks()
        # For 'unwanted touches', when a new command is received, old callbacks are discarded

        if isinstance(self.USAGE, str):
            update.effective_message.reply_text("Usage:\n" + "- " + self.USAGE,
                                                parse_mode=telegram.ParseMode.MARKDOWN)
            return

        elif not len(context.args) or context.args[0].lower() not in self.USAGE:
            methods_list = []
            description_list = []

            for module_name, module_description in self.USAGE.items():
                module_command = "/" + self.NAME + " " + module_name
                methods_list.append(module_command)
                description_list.append(f"`{module_command}`" + " - " + module_description)

            module_keyboard = [methods_list[i * 2:(i + 1) * 2] for i in range((len(methods_list) + 2 - 1) // 2)]
            reply_markup = telegram.ReplyKeyboardMarkup(module_keyboard,
                                                        resize_keyboard=True,
                                                        one_time_keyboard=True)

            update.effective_message.reply_text("Usage:\n" + "\n".join(description_list),
                                                reply_markup=reply_markup,
                                                parse_mode=telegram.ParseMode.MARKDOWN)
            return

        context.args[0] = context.args[0].lower()
        return self.command(update, context)

    # Build module utils (scripts, config, ...)
    @staticmethod
    def _build_utils():
        pass
