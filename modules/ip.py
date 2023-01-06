import humanize
import telegram
from datetime import datetime

from modules import RaspOneBaseModule


class ModuleIp(RaspOneBaseModule):

    NAME = "ip"
    DESCRIPTION = "Get public IP address of the server"

    USAGE = {
        "get": "Get IP address\n"
               "_More_: `/ip get ipv6`",
        "list": "Get list of previous logged IP addresses"
    }

    def __init__(self, core):
        super().__init__(core)

        self.api_url = "https://api.ipify.org"
        self.api64_url = "https://api64.ipify.org"

        self.history = []
        self.last_ip = self.prev_ip = None

    async def command(self, update, context):
        message = ""
        if context.args[0] == "get":
            ipv6 = False

            if len(context.args) == 2 and context.args[1] == "ipv6":
                ipv6 = True

            ip, err = self.get_ip_address(ipv6)
            if err:
                message = "😨 " + err

            else:
                message = "💻 IP: `%s`" % ip

                if not len(self.history):
                    self.history.append((ip, datetime.now()))

                elif ip != self.history[-1][0]:
                    self.history.append((ip, datetime.now()))

                    message += "\nPrevious IP was `%s` (%s ago)" % (
                        self.history[-2][0],
                        humanize.precisedelta(self.history[-2][1] - self.history[-1][1])
                    )

        elif context.args[0] == "list":
            message = "IP History:\n" + \
                      (("\n".join(f"💻 IP `{x[0]}` - {humanize.naturaldate(x[1])}" for x in self.history))
                       if len(self.history) else "_Empty_")

        await update.effective_message.reply_text(message, parse_mode=telegram.constants.ParseMode.MARKDOWN)

    def get_ip_address(self, ipv6=False):
        curl_response, request_id = self.network.curl(self.api64_url if ipv6 else self.api_url, parse_json=False)
        if not curl_response:
            return None, self.network.get_error(request_id)

        ip_addr = curl_response.text.replace("\n", "")
        return ip_addr, None
