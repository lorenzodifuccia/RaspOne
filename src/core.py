import sys
import pkgutil
import logging
import importlib
import traceback


import telegram
from telegram.chataction import ChatAction
from telegram.ext import Updater, CommandHandler

from src import config, DEFAULT_NAME, MODULES_PATH, PERSONAL_MODULES_PATH
from src.ipc import IPC
from src.server import Server

import modules

module_logger = logging.getLogger(DEFAULT_NAME + ".core")


# Core
class RaspOne:
    """
    RaspOne
    """

    HELP_MESSAGE = "Hi!!! 😊👋👋\nThe following modules are available:\n"

    def __init__(self):
        self.bot_token = config["Telegram"]["BotToken"]
        self.chat_id = config["Telegram"]["ChatId"]

        self.log(logging.INFO, "** STARTING **")

        self.ipc = None
        self.server = None

        self.modules = {
            "instances": dict(),
            "handlers": dict(),
            "callbacks": dict()
        }

        self.bot = None
        self.updater = None
        if not self._boot_telegram_bot():
            raise RaspOneException("Unable to boot Telegram Bot.")

        if not self._boot_telegram_updater():
            raise RaspOneException("Unable to boot Telegram Updater.")

    def start(self, restart=False):
        if restart:
            self.log(logging.WARNING, "Restarting...")

        if not self.ipc:
            self.ipc = IPC()

        if not self.server:
            self.server = Server()

        self._register_error()
        self._import_modules(restart)
        self.load_modules()

        self.send_message("Hello! 👋👋")

    # Telegram
    def _boot_telegram_bot(self):
        try:
            self.bot = telegram.Bot(self.bot_token)
            return True

        except telegram.TelegramError:
            self.log(logging.ERROR, "Telegram Boot Error!", exc_info=True, stack_info=True)
            return False

    def _boot_telegram_updater(self):
        try:
            self.updater = Updater(self.bot_token, use_context=True)
            return True

        except telegram.TelegramError:
            self.log(logging.ERROR, "Updater Boot Error!", exc_info=True, stack_info=True)
            return False

    # Modules
    @staticmethod
    def _import_modules(reload=False):
        # Dynamically load submodules (subclass of RaspOneBaseModule).
        # Ref: https://www.bnmetrics.com/blog/dynamic-import-in-python3
        for _, name, _ in pkgutil.iter_modules([MODULES_PATH, PERSONAL_MODULES_PATH]):
            if reload:
                try:
                    imported_module = importlib.reload(sys.modules["modules." + name])

                except (ImportError, ModuleNotFoundError, KeyError):
                    imported_module = importlib.reload(sys.modules["personal_modules." + name])

            else:
                try:
                    imported_module = importlib.import_module("modules." + name, package="modules")

                except (ImportError, ModuleNotFoundError):
                    imported_module = importlib.import_module('personal_modules.' + name, package="personal_modules")

            for i in dir(imported_module):
                attribute = getattr(imported_module, i)

                if isinstance(attribute, type) and issubclass(attribute, modules.RaspOneBaseModule) \
                        and attribute != modules.RaspOneBaseModule:
                    setattr(sys.modules["modules"], attribute.__name__, attribute)

    def load_modules(self):
        if len(self.modules["instances"]):
            self.kill_modules()

        for module in self._get_modules_list():
            module_instance = module(self)
            self.modules["instances"].update({module_instance.NAME: module_instance})

            command_handler = CommandHandler(module_instance.NAME,
                                             self.wrap_handler(module_instance.NAME, module_instance.default_handler))
            self.updater.dispatcher.add_handler(command_handler)
            self.modules["handlers"].update({module_instance.NAME: command_handler})

        self._register_help()

    @staticmethod
    def _get_modules_list():
        return set(filter(
            lambda m: isinstance(m, type) and issubclass(m, modules.RaspOneBaseModule)
            and m != modules.RaspOneBaseModule,
            map(lambda n: getattr(modules, n), dir(modules))
        ))

    # Help
    def _register_help(self):
        if "help" in self.modules["handlers"]:
            self.updater.dispatcher.remove_handler(self.modules["handlers"]["help"])

        help_handler = CommandHandler("help", self.wrap_handler("help", self._handle_help))
        self.modules["handlers"].update({"help": help_handler})
        self.updater.dispatcher.add_handler(help_handler)

    def _handle_help(self, update, _):
        commands_list = []
        description_list = []

        for module in self.modules["instances"].values():
            commands_list.append("/" + module.NAME)
            description_list.append("/" + module.NAME + " - " + module.DESCRIPTION)

        description_list.append("/help - Print this message")

        help_keyboard = [commands_list[i * 2:(i + 1) * 2] for i in range((len(commands_list) + 2 - 1) // 2)]
        reply_markup = telegram.ReplyKeyboardMarkup(help_keyboard, resize_keyboard=True)

        update.effective_message.reply_text(self.HELP_MESSAGE + "\n".join(description_list),
                                            reply_markup=reply_markup,
                                            parse_mode=telegram.ParseMode.MARKDOWN)

    # Callback Handlers
    def register_query_callback(self, callback_name, callback):
        query_handler = telegram.ext.CallbackQueryHandler(self.wrap_handler(callback_name, callback))
        self.updater.dispatcher.add_handler(query_handler)
        self.modules["callbacks"].update({callback_name: query_handler})

    def register_message_callback(self, callback_name, callback, message_filter=None):
        query_handler = telegram.ext.MessageHandler(message_filter if message_filter
                                                    else telegram.ext.filters.Filters.all,
                                                    self.wrap_handler(callback_name, callback))
        self.updater.dispatcher.add_handler(query_handler)
        self.modules["callbacks"].update({callback_name: query_handler})

    def remove_callback(self, callback_name):
        if callback_name in self.modules["callbacks"]:
            query_handler = self.modules["callbacks"].pop(callback_name)
            self.updater.dispatcher.remove_handler(query_handler)

    def remove_callbacks(self):
        for callback_name in list(self.modules["callbacks"].keys()):
            self.remove_callback(callback_name)

    # Handler Wrapper and Decorator
    @staticmethod
    def wrap_handler(callback_tag, func):
        """
        This wrapper is used with CommandHandler and CallbackQueryHandler objects in order to wrap their callback.
        """
        def wrapped(update, context, *args, **kwargs):
            # Authenticate the user
            user_id = update.effective_user.id
            if str(user_id) != config["Telegram"]["ChatId"]:
                module_logger.warning("[SEC] Unauthorized access denied for: %s (%s)" %
                                      (update.effective_user.name, user_id))
                return

            # Check if CALLBACK_QUERY is actually for this module
            if update.callback_query and len(update.callback_query.data):
                if not update.callback_query.data.startswith(callback_tag.upper()):
                    return

                update.callback_query.data = update.callback_query.data.replace(callback_tag.upper() + "_", "")

            # Add the TYPING action to the bot while processing the callback
            context.bot.send_chat_action(chat_id=config["Telegram"]["ChatId"], action=ChatAction.TYPING)

            return func(update, context, *args, **kwargs)

        return wrapped

    # Log + Send Message
    def log(self, lvl, msg: str, network_error=False, *args, **kwargs):
        """
        Logging function.
        If the logging level (lvl parameter) is " > logging.INFO", it will send the log message also via bot chat.
        General configuration of the logging library present in the main (`rasp_one.py`).
        """
        if lvl > logging.INFO and not network_error:
            try:
                self.send_message(
                    ("😧 Warning 😧" if lvl == logging.WARNING else
                     ("😨 ERROR 😰" if lvl == logging.ERROR else "😱 CRITICAL 😱")) + "\n" +
                    msg[:telegram.constants.MAX_MESSAGE_LENGTH - 4] +
                    ("" if len(msg) < telegram.constants.MAX_MESSAGE_LENGTH else "..."),
                    log=False,
                    markdown=False
                )

            except (telegram.TelegramError, Exception):
                pass

        module_logger.log(lvl, "[R1] " + msg, *args, **kwargs)

    def send_message(self, message: str, log=True, markdown=True):
        try:
            if log:
                self.log(logging.INFO, "Sending message: %s" % message)

            self.bot.send_message(self.chat_id, message,
                                  parse_mode=telegram.ParseMode.MARKDOWN if markdown else None,
                                  reply_markup=telegram.ReplyKeyboardRemove())
            return True

        except telegram.TelegramError as send_error:
            self.log(logging.ERROR, "Send message error! Reason: %s" % send_error, exc_info=True, stack_info=True)
            return False

    # Errors
    def _register_error(self):
        self.updater.dispatcher.add_error_handler(self._error_handler)

    def _error_handler(self, update, context):
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = '\n'.join(tb_list)
        self.log(lvl=logging.ERROR,
                 msg="Update ID '%s' caused error: %s" % (update.update_id if update else "N/A", tb_string),
                 network_error=isinstance(context.error, telegram.error.NetworkError))

    # Killing
    def restart(self):
        self.kill()
        self.start(restart=True)

    def kill(self):
        self.kill_modules()

        for k in list(self.modules["handlers"].keys()):
            handler = self.modules["handlers"].pop(k)
            self.updater.dispatcher.remove_handler(handler)
            self.log(logging.INFO, "Deleted handler: %s (%s)" % (k, handler))

        self.remove_callbacks()

        self.server.kill()
        self.ipc.kill()

        self.log(logging.WARNING, "Killed...")

    def kill_modules(self):
        self.log(logging.DEBUG, "Deleting %d modules" % len(self.modules["instances"]))
        for m in list(self.modules["instances"].keys()):
            self.kill_module(m)

    def kill_module(self, module_name):
        if module_name not in self.modules["instances"]:
            self.log(logging.WARNING, "Deleting not loaded module: %s", module_name)
            return

        module_instance = self.modules["instances"].pop(module_name)
        self.updater.dispatcher.remove_handler(self.modules["handlers"].pop(module_name))

        if module_name in self.ipc.services:
            self.ipc.remove_service(module_name)

        self.log(logging.INFO, "Deleted module: %s" % module_instance)

    def terminate(self):
        self.kill()
        self.ipc.terminate()
        self.updater.stop()
        self.log(logging.WARNING, "Terminated...")


# Exception
class RaspOneException(Exception):
    """Custom exception to catch in the main thread, raised by the code for a specific reason.
    Any exception different from this one are raised by unhandled program failures."""
