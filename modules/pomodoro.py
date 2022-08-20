import datetime
import humanize

from modules import RaspOneBaseModule


class ModulePomodoro(RaspOneBaseModule):

    NAME = "pomodoro"
    DESCRIPTION = "Focus with your Pomodoro Timer."
    USAGE = {
        "start": "Start the timer (default 20 mins)\n"
                 "_More_: `/pomodoro start <min> <msg>`, _i.e._ `/pomodoro start 15 Breaaaaak!`",
        "status": "Get current timer status",
        "stop": "Stop the timer"
    }

    def __init__(self, core):
        super().__init__(core)

        self.default_message = "POMODORO!! ⏰🍅"
        self.timer_message = self.default_message

        self.interval = 20

        self.updater_job = None
        self.last_timer = None

    def command(self, update, context):
        if context.args[0] == "stop":
            self.stop_job()
            update.effective_message.reply_text("Pomodoro ⏰ OFF")
            return

        elif context.args[0] == "status":
            message = "Pomodoro ⏰  is currently "
            if not self.updater_job:
                message += "OFF"

            else:
                message += "ON\nNext timer will be in: " + humanize.precisedelta(
                    datetime.datetime.now() - (self.last_timer + datetime.timedelta(minutes=self.interval))
                )

            update.effective_message.reply_text(message)
            return

        self.interval = 20
        self.timer_message = self.default_message

        context.args.pop(0)
        if len(context.args) and context.args[0].isdigit():
            self.interval = int(context.args.pop(0))

        if len(context.args):
            self.timer_message = " ".join(context.args)

        self.start_job()
        update.effective_message.reply_text("Pomodoro ⏰ ON: set to %s minutes" % self.interval)

    def start_job(self):
        self.stop_job()
        self.last_timer = datetime.datetime.now()
        self.updater_job = self.core.updater.job_queue.run_repeating(self.updater, interval=self.interval * 60)

    def stop_job(self):
        if self.updater_job:
            self.updater_job.schedule_removal()

        self.updater_job = None

    def updater(self, _):
        self.last_timer = datetime.datetime.now()
        self.core.send_message(self.timer_message, markdown=True)
