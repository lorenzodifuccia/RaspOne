import json
import base64
import logging
import datetime
import telegram
import humanize

from typing import Union

from src import config, DEFAULT_NAME
from modules import RaspOneBaseModule

module_logger = logging.getLogger(DEFAULT_NAME + ".module.torrent")


class ModuleTorrent(RaspOneBaseModule):

    NAME = "torrent"
    DESCRIPTION = "Start and manage torrents on Transmission"

    USAGE = {
        "status": "Check if `transmission` is running",
        "list": "List torrents",
        "add": "Add a torrent from a file or a magnet link",
        "remove": "Remove a torrent (keeping local data)",
        "pause": "Pause or resume a torrent"
    }

    def __init__(self, core):
        super().__init__(core)

        self.rpc_url = "http://127.0.0.1:9091/transmission/rpc"
        if config["Module - Torrent"]["RPCUrl"] != "None":
            self.rpc_url = config["Module - Torrent"]["RPCUrl"]

        self.download_dir = config["Module - Torrent"]["DownloadDir"]

        self.transmission_service_name = "transmission"

        self.watcher = None
        self.watcher_timer = datetime.timedelta(seconds=15)
        self._watcher_set = set()
        self.start_watcher()

    async def command(self, update, context):
        self.start_watcher()

        markdown = telegram.constants.ParseMode.MARKDOWN
        keyboard = None

        if context.args[0] == "status":
            status, error = self.core.server.is_process_running(self.transmission_service_name)
            if error:
                message = error
                markdown = None

            else:
                message = "`transmission` is %srunning %s" % \
                          ("" if status else "**not** ", "👍" if status else "👎")

        elif context.args[0] in ["list", "pause", "remove"]:
            torrents, error = self.get_torrent_list()
            if error:
                message = error
                markdown = None

            else:
                message = self._list_torrents(torrents)

                if context.args[0] == "list" or not len(torrents):
                    message = "📥 Torrents:\n" + message

                else:
                    if context.args[0] == "pause":
                        message = "📥 Which torrent do you want to pause/resume?\n" + message
                        self.register_query_callback("PAUSE", self.query_handler_pause)

                    else:
                        message = "📥 Which torrent do you want to *remove*?\n" + message
                        self.register_query_callback("REMOVE", self.query_handler_remove)

                    keyboard = self._prepare_keyboard(context.args[0].upper(), torrents)

        else:
            message = "📥 Do you want to add a torrent?\n" \
                      "Waiting a `magnet:` URL or `.torrent` file..."

            self.register_message_callback("ADD", self.message_handler_add)

        await update.effective_message.reply_text(message, reply_markup=keyboard, parse_mode=markdown)

    async def query_handler_pause(self, update, _):
        query = update.callback_query
        torrents, error = self.get_torrent(query.data)
        if error:
            message = error

        else:
            torrent = torrents.pop(0)
            status, error = self.start_torrent(torrent) if not torrent["status"] else self.pause_torrent(torrent)
            if error:
                message = error

            else:
                message = "👍"

        await query.edit_message_text(text=message)
        self.remove_callback("PAUSE")

    async def query_handler_remove(self, update, _):
        query = update.callback_query
        torrents, error = self.get_torrent(query.data)
        if error:
            message = error

        else:
            torrent = torrents.pop(0)
            status, error = self.remove_torrent(torrent)
            if error:
                message = error

            else:
                message = "👍"

        await query.edit_message_text(text=message)
        self.remove_callback("REMOVE")

    async def message_handler_add(self, update, _):
        torrent = None
        markdown = None
        message = "Error: invalid torrent file/URL!"
        if update.effective_message.text:
            if update.effective_message.text.startswith("magnet:"):
                torrent = update.effective_message.text

        elif update.effective_message.document:
            if "torrent" in update.effective_message.document.mime_type:
                torrent = update.effective_message.document.get_file().download_as_bytearray()

        if torrent:
            status, error = self.add_torrent(torrent)
            if error:
                message = error

            else:
                message = "Torrent {state} 👍\n" \
                          "#*{id}* - `{name}`".format_map(status)
                markdown = telegram.constants.ParseMode.MARKDOWN

        await update.effective_message.reply_text(message, parse_mode=markdown)
        self.remove_callback("ADD")

    # Watcher/Updater
    def start_watcher(self):
        self.stop_watcher()
        self.watcher = self.core.application.job_queue.run_repeating(self.watch_torrent, interval=self.watcher_timer)

    def stop_watcher(self):
        if self.watcher:
            self.watcher.schedule_removal()

        self.watcher = None

    async def watch_torrent(self, _):
        if not self.watcher:  # Kill switch
            self.stop_watcher()
            return

        torrents, error = self.get_torrent_list()
        if not error and len(torrents):
            if len(self._watcher_set):
                completed = {x["id"] for x in torrents if x["percentDone"] == 1}
                for completed_id in self._watcher_set.intersection(completed):
                    completed_torrent = next(x for x in torrents if x["id"] == completed_id)
                    self.core.send_message("📥 Torrent Completed 🎉\n"
                                           "#*{id}* - `{name}`".format_map(completed_torrent),
                                           markdown=True)

                self._watcher_set.clear()

            self._watcher_set.update(x["id"] for x in torrents if x["percentDone"] < 1)
            if len(self._watcher_set):
                self.watcher.job.trigger.interval = self.watcher_timer
                return

        self.watcher.job.trigger.interval = min(self.watcher.job.trigger.interval + datetime.timedelta(seconds=30),
                                                datetime.timedelta(minutes=5))

    # RPC API
    def get_torrent_list(self):
        rpc_response, err = self.rpc("torrent-get", {"fields": ["id", "name", "totalSize", "error",
                                                                "errorString", "eta", "percentDone",
                                                                "status", "totalSize"]})
        if err:
            return False, err

        elif rpc_response["result"] != "success":
            return False, "Error: %s result:\n%s" % (rpc_response["result"], json.dumps(rpc_response))

        return rpc_response["arguments"]["torrents"], None

    def get_torrent(self, torrent_id):
        rpc_response, err = self.rpc("torrent-get", {
            "fields": ["id", "name", "totalSize", "error",
                       "errorString", "eta", "percentDone",
                       "status", "totalSize"],
            "ids": [int(torrent_id)]
        })
        if err:
            return False, err

        elif rpc_response["result"] != "success":
            return False, "Error: %s result:\n%s" % (rpc_response["result"], json.dumps(rpc_response))

        return rpc_response["arguments"]["torrents"], None

    def start_torrent(self, torrent):
        rpc_response, err = self.rpc("torrent-start", {"ids": [torrent["id"]]})
        if err:
            return False, err

        elif rpc_response["result"] != "success":
            return False, "Error: %s result:\n%s" % (rpc_response["result"], json.dumps(rpc_response))

        return True, None

    def pause_torrent(self, torrent):
        rpc_response, err = self.rpc("torrent-stop", {"ids": [torrent["id"]]})
        if err:
            return False, err

        elif rpc_response["result"] != "success":
            return False, "Error: %s result:\n%s" % (rpc_response["result"], json.dumps(rpc_response))

        return True, None

    def remove_torrent(self, torrent):
        rpc_response, err = self.rpc("torrent-remove", {"ids": [torrent["id"]],
                                                        "delete-local-data": True if torrent["status"] == 4 else False})
        if err:
            return False, err

        elif rpc_response["result"] != "success":
            return False, "Error: %s result:\n%s" % (rpc_response["result"], json.dumps(rpc_response))

        return True, None

    def add_torrent(self, torrent_source: Union[str, bytearray]):
        arguments = {"download-dir": self.download_dir, "paused": False}
        if isinstance(torrent_source, str):
            arguments.update({"filename": torrent_source})

        else:
            arguments.update({"metainfo": base64.b64encode(torrent_source).decode()})

        rpc_response, err = self.rpc("torrent-add", arguments)
        if err:
            return False, err

        elif rpc_response["result"] != "success":
            return False, "Error: %s result.\nResponse: %s" % (rpc_response["result"], json.dumps(rpc_response))

        if "torrent-added" in rpc_response["arguments"]:
            torrent_info = rpc_response["arguments"]["torrent-added"]
            torrent_info["state"] = "added"

        else:
            torrent_info = rpc_response["arguments"]["torrent-duplicate"]
            torrent_info["state"] = "duplicate"

        return torrent_info, None

    def rpc(self, method, arguments=None):
        rpc_req_response, request_id = self.network.curl(self.rpc_url,
                                                         method="post",
                                                         json={"method": method, "arguments": arguments},
                                                         check_200=False,
                                                         parse_json=False)
        if rpc_req_response is False:
            # `if not rpc_req_response` makes requests check `response.ok`
            return None, self.network.get_error(request_id)

        if rpc_req_response.status_code == 409:
            self.network.session.headers.update({
                "X-Transmission-Session-Id": rpc_req_response.headers["X-Transmission-Session-Id"]
            })
            return self.rpc(method, arguments)

        elif rpc_req_response.status_code != 200:
            return None, "Error while performing this request:\n" + self.network.get_request_details(request_id)

        rpc_response = self.network.safe_json(rpc_req_response)
        if not rpc_response:
            return None, "Error parsing RPC response:\n" + self.network.get_request_details(request_id)

        return rpc_response, None

    # Utils
    @staticmethod
    def _list_torrents(torrents):
        torrent_list_msg = ""
        if not len(torrents):
            torrent_list_msg = "_Empty_"

        for torrent in torrents:
            torrent_list_msg += "\n"
            torrent_list_msg += "#*{id}* - `{name}`\n".format_map(torrent)
            torrent_list_msg += "Status: %s\n" % STATUS_MAP[torrent["status"]]
            torrent_list_msg += "ETA: %s - " % \
                                (humanize.naturaltime(torrent['eta'], future=True)
                                 if torrent['eta'] > 0 else torrent['eta'])
            torrent_list_msg += "Percent: %s%%\n" % round(torrent["percentDone"] * 100, 2)
            torrent_list_msg += "Size: %s\n" % humanize.naturalsize(torrent["totalSize"])

            if torrent["error"]:
                torrent_list_msg += "**ERROR**: _{errorString}_\n".format_map(torrent)

        return torrent_list_msg

    @staticmethod
    def _prepare_keyboard(tag, torrents):
        torrent_list = []
        for torrent in torrents:
            torrent_list.append(telegram.InlineKeyboardButton(str(torrent["id"]),
                                                              callback_data=f"TORRENT_{tag}_{torrent['id']}"))

        return telegram.InlineKeyboardMarkup(
            [torrent_list[i * 2:(i + 1) * 2] for i in range((len(torrent_list) + 2 - 1) // 2)]
        )


STATUS_MAP = {
    0: "Stopped",
    1: "Queued to verify local data",
    2: "Verifying local data",
    3: "Queued to download",
    4: "*Downloading*",
    5: "Queued to seed",
    6: "Seeding"
}
