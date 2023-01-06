import asana
import logging

from src import config, DEFAULT_NAME
from modules import RaspOneBaseModule

module_logger = logging.getLogger(DEFAULT_NAME + ".module.asana")


class ModuleAsana(RaspOneBaseModule):

    NAME = "asana"
    DESCRIPTION = "Run Asana scripts"

    USAGE = {
        "assign": "Assign-to-me all new tasks"
    }

    def __init__(self, core):
        super().__init__(core)

        self.access_token = config["Module - Asana"]["AccessToken"] \
            if config["Module - Asana"]["AccessToken"] != "None" else None

        self.client = self.me = None

        if self.access_token:
            try:
                self.client = asana.Client.access_token(self.access_token)
                self.me = self.client.users.me()

            except (ValueError, Exception):
                module_logger.error("[Asana] Login error!", exc_info=True, stack_info=True)

    async def command(self, update, context):
        if context.args[0] == "assign":
            if not self.access_token:
                message = "Access Token not configured. Configure it on the configuration file of RaspOne."

            else:
                ret_code = self._assign_to_me()
                if not ret_code[0]:
                    message = ret_code[1]

                else:
                    message = ret_code[1] + "\nDone! 👍"

            await update.effective_message.reply_text(message)

    def _assign_to_me(self):
        tasks = []
        projects = []
        workspaces = list(self.client.workspaces.get_workspaces())
        for w in workspaces:
            projects.extend(list(self.client.projects.get_projects({"archived": False, "workspace": w["gid"]})))

        for p in projects:
            tasks.extend(list(self.client.tasks.get_tasks_for_project(p["gid"], opt_fields=["assignee", ["name"]])))

        new_tasks = list(filter(lambda t: not t["assignee"] or t["assignee"]["gid"] != self.me["gid"], tasks))
        if not len(new_tasks):
            return True, "All tasks already assigned! 📋"

        return_strings = ""
        for task in new_tasks:
            try:
                self.client.tasks.update_task(task["gid"], {"assignee": self.me["gid"]})

            except (ConnectionError, Exception):
                module_logger.error("[Asana] Assign task error!", exc_info=True, stack_info=True)
                return False, "😵 Error while assigning a task. See complete log..."

            return_strings += f"✅ New assignment 👉 {task['name']}!\n"

        return True, return_strings
