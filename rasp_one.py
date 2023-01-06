import os
import datetime

import logging
from logging.handlers import RotatingFileHandler

from src import config, DEFAULT_NAME, LOGS_PATH
from src.core import RaspOne, RaspOneException


def main():
    main_logger = logging.getLogger(DEFAULT_NAME)
    main_logger.setLevel(int(config["General"]["DebugLevel"]))
    file_handler = RotatingFileHandler(
        filename=os.path.join(LOGS_PATH, "raspOne_%s.log" % (datetime.datetime.now().strftime("%Y-%m-%d"))),
        maxBytes=1024 * 1024 * 1024
    )

    file_handler.setFormatter(logging.Formatter('[%(asctime)s] (%(levelname)s) %(name)s: %(message)s'))
    main_logger.addHandler(file_handler)

    attempt = 0
    reset_attempt = datetime.datetime.now()
    terminated = False
    while attempt < 5 and not terminated:
        try:
            rasp_one = RaspOne()
            rasp_one.start()
            rasp_one.application.run_polling(close_loop=False)
            rasp_one.terminate()
            terminated = True

        except RaspOneException as handled_exception:
            main_logger.error("Error in main: %s" % handled_exception, exc_info=True, stack_info=True)

        except Exception as unhandled_exception:
            main_logger.error("Unhandled error in main: %s" % unhandled_exception, exc_info=True, stack_info=True)

        finally:
            if datetime.datetime.now() - reset_attempt > datetime.timedelta(minutes=60):
                attempt = 0
                reset_attempt = datetime.datetime.now()

            else:
                attempt += 1

    else:
        main_logger.critical("Aborting...", exc_info=True, stack_info=True)


if __name__ == "__main__":
    main()
