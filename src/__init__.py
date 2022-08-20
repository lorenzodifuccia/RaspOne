import os
import configparser

DEFAULT_NAME = "raspOne"

BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # '/src/../'
LOGS_PATH = os.path.join(BASE_PATH, "logs/")
UTILS_PATH = os.path.join(BASE_PATH, "utils/")
MODULES_PATH = os.path.join(BASE_PATH, "modules")
PERSONAL_MODULES_PATH = os.path.join(BASE_PATH, "personal_modules")

# Create logs/ and utils/ dirs
if not os.path.isdir(LOGS_PATH):
    os.mkdir(LOGS_PATH)

if not os.path.isdir(UTILS_PATH):
    os.mkdir(UTILS_PATH)

# Parse config
config = configparser.ConfigParser()

CONFIG_PATH = os.path.join(BASE_PATH, "personal_rasp_conf.ini")
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = os.path.join(PERSONAL_MODULES_PATH, "personal_rasp_conf.ini")
    if not os.path.exists(CONFIG_PATH):
        CONFIG_PATH = os.path.join(BASE_PATH, "rasp_conf.ini")

config.read(CONFIG_PATH)
