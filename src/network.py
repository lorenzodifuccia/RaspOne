import json
import random
import logging
import requests
import threading
import cachetools
from typing import Tuple, Union

from src import config, DEFAULT_NAME

module_global_logger = logging.getLogger(DEFAULT_NAME + ".network")
_global_request_stack = cachetools.TTLCache(maxsize=1024, ttl=600)


class Network:
    # TODO:
    #  1. Log in case of error [WORKING ON, NEED TO TEST IT]

    COMMON_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:67.0) Gecko/20100101 Firefox/67.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    REQUEST_NOT_BUILT = 1
    REQUEST_SENDING_ERROR = 2
    UNEXPECTED_RESPONSE_CODE = 3
    JSON_DECODE_ERROR = 4

    ERROR_DETAIL = "See internal log for further details (ID: %d)."

    ERRORS = {
        REQUEST_NOT_BUILT: "Error during request building. " + ERROR_DETAIL,
        REQUEST_SENDING_ERROR: "Error during request sending. " + ERROR_DETAIL,
        UNEXPECTED_RESPONSE_CODE: "Response code differs from 200 OK. " + ERROR_DETAIL,
        JSON_DECODE_ERROR: "Response body is not a valid JSON. " + ERROR_DETAIL,
    }

    def __init__(self, module_name):
        self.module_name = module_name
        self.module_logger = logging.getLogger(DEFAULT_NAME + ".network:" + module_name)

        self.session = requests.Session()
        if config["Network"]["Proxy"] != "False":
            self.session.proxies = json.loads(config["Network"]["Proxy"])

            if config["Network"]["Insecure"] != "False":
                self.session.verify = False

        self.reset_headers()

        self.request_stack = _global_request_stack
        self.request_stack_lock = threading.Lock()

    def reset_headers(self):
        self.session.headers = self.COMMON_HEADERS.copy()

        if config["Network"]["UserAgent"] != "None":
            self.session.headers["User-Agent"] = config["Network"]["UserAgent"]

    # Request Stack
    def _save_request_stack(self, request_id, **kwargs):
        self.request_stack_lock.acquire()
        try:
            if request_id not in self.request_stack:
                self.request_stack.update({request_id: dict()})

            self.request_stack[request_id].update(kwargs)

            if "err" in kwargs:
                try:
                    self.module_logger.warning("[cURL] Error in request/response: " +
                                               self.get_error(request_id) + "\n" +
                                               self.get_request_details(request_id))
                except UnicodeError:
                    self.module_logger.warning("[cURL] Error logging request", exc_info=True, stack_info=True)

        except KeyError:
            self.module_logger.error("[cURL] Error saving request on cache", exc_info=True, stack_info=True)

        finally:
            self.request_stack_lock.release()

    def get_request_details(self, request_id):
        req_obj = self.request_stack.get(request_id, default=False)
        if req_obj is False:  # not req_obj, but then PyCharm failed to understand the type...
            return "Details N/A"

        output = ""
        if "req" in req_obj:
            output += "-- REQUEST %d --\n" % request_id + \
                      req_obj["req"].method.upper() + ' ' + req_obj["req"].url + "\n" + \
                      ('\n'.join('{}: {}'.format(k, v) for k, v in req_obj["req"].headers.items())
                       if req_obj["req"].headers else "") + "\n" + \
                      ('\n'.join('{}: {}'.format(k, v) for k, v in req_obj["req"]._cookies.items())  # PrepareRequest
                       if req_obj["req"]._cookies else "") + "\n" + \
                      (str(req_obj["req"].body) if hasattr(req_obj["req"], "body") and len(req_obj["req"].body) else "")

        if "res" in req_obj:
            output += "-- RESPONSE %d --\n" % request_id + \
                      str(req_obj["res"].status_code) + ' ' + req_obj["res"].reason + "\n" + \
                      ('\n'.join('{}: {}'.format(k, v) for k, v in req_obj["res"].headers.items())
                       if req_obj["res"].headers else "") + "\n" + \
                      ('\n'.join('{}: {}'.format(k, v) for k, v in req_obj["res"].cookies.items())
                       if req_obj["res"].cookies else "") + "\n" + \
                      (req_obj["res"].text if hasattr(req_obj["res"], "text") and len(req_obj["res"].text) else "")

        return output

    def get_error(self, request_id):
        id_str = " (ID: %d)" % request_id

        req_obj = self.request_stack.get(request_id, default=False)
        if not req_obj:
            return "<Request ID not found>" + id_str

        err_str = req_obj.get("err", False)
        if not err_str:
            return "<Request ID has no errors>" + id_str

        elif err_str not in self.ERRORS:
            return "<Invalid error>" + id_str

        return self.ERRORS[err_str] % request_id

    # Network
    def curl(self, url, method="get", check_200=True, parse_json=True, **kwargs) \
            -> Tuple[Union[requests.Response, bool], int]:
        request_id = random.randint(11111111, 99999999)

        self.module_logger.debug(
            "[cURL] Building new request for: %s (method: %s, 200: %s, JSON: %s, kwargs: %s) [ID: %s]" %
            (url, method.upper(), check_200, parse_json, kwargs, request_id))

        try:
            request = self.session.prepare_request(requests.Request(method, url, **kwargs))

        except (ValueError, TypeError, Exception):
            self.module_logger.error("[cURL] Unable to build/prepare request object. [ID %s]" % request_id,
                                     exc_info=True, stack_info=True)
            self._save_request_stack(request_id, err=self.REQUEST_NOT_BUILT)
            return False, request_id

        self._save_request_stack(request_id, req=request)

        try:
            response = self.session.send(request)

        except (requests.RequestException, requests.ConnectionError, requests.HTTPError,
                ConnectionError, ValueError, Exception):
            self.module_logger.error("[cURL] Unable to send request. [ID %s]"
                                     % request_id, exc_info=True, stack_info=True)
            self._save_request_stack(request_id, err=self.REQUEST_SENDING_ERROR)
            return False, request_id

        self._save_request_stack(request_id, res=response)

        if check_200 and response.status_code != 200:
            self.module_logger.warning("[cURL] Response code != 200. [ID %s]" % request_id)
            self._save_request_stack(request_id, err=self.UNEXPECTED_RESPONSE_CODE)
            return False, request_id

        elif "Content-Type" in response.headers \
                and "application/json" in response.headers["Content-Type"] \
                and parse_json:
            decoded_json = self.safe_json(response)
            if not decoded_json:
                self.module_logger.warning("[cURL] Response not a JSON. [ID %s]" % request_id)
                self._save_request_stack(request_id, err=self.JSON_DECODE_ERROR)
                return False, request_id

            self._save_request_stack(request_id, json=decoded_json)
            return decoded_json, request_id

        return response, request_id

    @staticmethod
    def safe_json(response):
        try:
            return response.json()

        except (ValueError, TypeError, json.JSONDecodeError):
            module_global_logger.warning("[SafeJson] unable to decode JSON response.", exc_info=True, stack_info=True)
            return False
