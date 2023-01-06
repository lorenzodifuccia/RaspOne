import uuid
import boto3
import logging
import telegram

from src import config, DEFAULT_NAME
from src.core import RaspOneException
from modules import RaspOneBaseModule


module_logger = logging.getLogger(DEFAULT_NAME + ".module.s3")


class ModuleS3(RaspOneBaseModule):
    """
    AWS - S3 Module

    Configuration:
    The following Action must be Allowed by the IAM policy of the user which will call the AWS API:
    ```
        "Action": [
                "s3:ListBucket",
                "s3:GetObject",
                "s3:GetObjectAttributes",
                "s3:PutObject",
                "s3:DeleteObject",
            ]
    ```
    """

    NAME = "s3"
    DESCRIPTION = "Save and manage objects on an AWS S3 bucket"

    USAGE = {
        "status": "Check if `s3` command is available",
        "list": "List objects on S3 bucket",
        "save": "Save object on S3 bucket",
        "delete": "Delete object from S3 bucket"
    }

    def __init__(self, core):
        super().__init__(core)

        self.session = False
        self.session_error_message = "No AWS Session available. Please see configuration file"

        self.rasp_bucket_name = config["Module - AWS"]["BucketName"]

        if config["Module - AWS"]["AccessKeyId"] != "None" \
                and config["Module - AWS"]["SecretAccessKey"] != "None":
            self.session = boto3.Session(aws_access_key_id=config["Module - AWS"]["AccessKeyId"],
                                         aws_secret_access_key=config["Module - AWS"]["SecretAccessKey"])

    async def command(self, update, context):
        markdown = telegram.constants.ParseMode.MARKDOWN
        keyboard = None

        if context.args[0] == "status" or not self.session:
            message = "`/s3` command is %s" % "available" if self.session \
                else "not available. Please see configuration file..."

        elif context.args[0] in ["list", "delete"]:
            objects, error = self.get_objects()
            if error:
                message = error
                markdown = None

            else:
                message = self._list_objects(objects)

                if context.args[0] == "list" or not len(objects):
                    message = "🪣 Objects:\n" + message

                else:
                    message = "🪣 Which object do you want to *delete*?\n" + message
                    self.register_query_callback("DELETE", self.query_handler_delete)
                    keyboard = self._prepare_keyboard("DELETE", objects)

        else:
            message = "🪣 Do you want to add an object?\nWaiting a file..."
            self.register_message_callback("ADD", self.message_handler_add)

        await update.effective_message.reply_text(message, reply_markup=keyboard, parse_mode=markdown)

    async def query_handler_delete(self, update, _):
        query = update.callback_query
        objects, error = self.get_objects()
        if error:
            message = error

        else:
            try:
                obj = next(filter(lambda o: o["Key"] == query.data, objects))
                status, error = self.delete_object(obj["Key"])
                if error:
                    message = error

                else:
                    message = "👍"

            except StopIteration:
                message = "Object not found (Key %s)" % query.data

        await query.edit_message_text(text=message)
        self.remove_callback("DELETE")

    async def message_handler_add(self, update, _):
        markdown = None
        message = "Error: expecting a file!"

        if update.effective_message.document:
            file_key = uuid.uuid4().urn[9:] + "/" + update.effective_message.document.file_name
            file_attached = await update.effective_message.document.get_file()
            file_bytearray = await file_attached.download_as_bytearray()
            status, error = self.add_object(file_key, file_bytearray, update.effective_message.document.mime_type)
            if error:
                message = str(error)

            else:
                message = "Object added 👍\n" \
                          f"• [{file_key}](https://{self.rasp_bucket_name}.s3.amazonaws.com/{file_key})"
                markdown = telegram.constants.ParseMode.MARKDOWN

        await update.effective_message.reply_text(message, parse_mode=markdown)
        self.remove_callback("ADD")

    # API
    def _check_session(self):
        if not self.session:
            raise RaspOneException(self.session_error_message)

    def get_objects(self):
        try:
            self._check_session()
            client = self.session.client("s3")

            return client.list_objects(Bucket=self.rasp_bucket_name).get("Contents", []), None

        except (RaspOneException, Exception) as error:
            return None, error

    def delete_object(self, object_key):
        try:
            self._check_session()
            client = self.session.client("s3")
            response = client.delete_object(Bucket=self.rasp_bucket_name, Key=object_key)
            return True, None

        except (RaspOneException, Exception) as error:
            return False, error

    def upload_file(self, object_name, filepath):
        pass

    def add_object(self, object_key: str, object_data: bytearray, object_mime=False):
        try:
            self._check_session()
            client = self.session.client("s3")
            response = client.put_object(Bucket=self.rasp_bucket_name, Key=object_key, Body=object_data,
                                         **({'ContentType': object_mime} if object_mime else {}))
            return True, None

        except Exception as error:
            return False, error

    # Utils
    def _list_objects(self, objects):
        if not len(objects):
            objects_list_msg = "_Empty_"

        else:
            objects_list_msg = "\n".join(f"• [{obj['Key']}](https://{self.rasp_bucket_name}.s3.amazonaws.com/{obj['Key']})"
                                         for obj in objects)

        return objects_list_msg

    @staticmethod
    def _prepare_keyboard(tag, objects):
        objects_list = []
        for obj in objects:
            objects_list.append(telegram.InlineKeyboardButton(str(obj["Key"]), callback_data=f"S3_{tag}_{obj['Key']}"))

        return telegram.InlineKeyboardMarkup(
            [objects_list[i * 2:(i + 1) * 2] for i in range((len(objects_list) + 2 - 1) // 2)]
        )
