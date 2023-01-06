import json
import logging
import threading
import socketserver

from src import DEFAULT_NAME, config

module_logger = logging.getLogger(DEFAULT_NAME + ".server")

_service_list = dict()
_service_list_lock = threading.Lock()


class IPC:
    def __init__(self):
        self.ipc_server = None
        self.thread = None

        self.services = _service_list
        self.lock = _service_list_lock

        self._start_ipc()

    def add_service(self, name, service_callback):
        self.lock.acquire()
        self.services.update({name: service_callback})
        module_logger.info("[IPC] Added service: %s (%s)" % (name, service_callback))
        self.lock.release()

    def remove_service(self, name):
        self.lock.acquire()
        try:
            self.services.pop(name)
        except KeyError:
            module_logger.info("[IPC] Trying to remove a service not found: %s" % name)
        else:
            module_logger.info("[IPC] Removed service: %s" % name)
        finally:
            self.lock.release()

    def kill(self):
        for s in list(self.services.keys()):
            self.remove_service(s)

    def terminate(self):
        self.ipc_server.shutdown()
        self.ipc_server.server_close()

    def _start_ipc(self):
        try:
            self.ipc_server = socketserver.ThreadingTCPServer(
                (config["Server"]["IPCAddress"], int(config["Server"]["IPCPort"])),
                IPCHandler
            )

        except OSError:
            module_logger.error("[IPC] OSError.", exc_info=True, stack_info=True)
            raise

        self.thread = threading.Thread(
            name="[Server] IPC",
            target=self.ipc_server.serve_forever
        )
        self.thread.start()


class IPCHandler(socketserver.BaseRequestHandler):
    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)
        self.services = None
        self.lock = None

    def setup(self):
        self.services = _service_list
        self.lock = _service_list_lock

    def handle(self):
        self.lock.acquire()

        try:
            recv = self.request.recv(1024)
            if not len(recv):
                self.request.close()

            message = json.loads(recv.decode())
            if "service" not in message:
                module_logger.error("[IPC] Service not in message: %s" % message)
                raise ValueError

            elif message["service"] not in self.services:
                module_logger.error("[IPC] Service not available: %s" % message)
                raise ValueError

            module_logger.info(
                "[IPC] Calling service %s: %s (%d)" % (message["service"], message, id(message))
            )
            result = self.services[message["service"]](message.get("message", None))
            self.request.sendall(json.dumps({"ok": result}).encode())
            module_logger.info("[IPC] Finished service %s: %d" % (message["service"], id(message)))

        except (ValueError, TypeError, json.JSONDecodeError):
            module_logger.error("[IPC] Handling error.", exc_info=True, stack_info=True)
            pass

        except (ConnectionResetError, BrokenPipeError, UnicodeEncodeError):
            module_logger.error("[IPC] Connection error.", exc_info=True, stack_info=True)
            self.request.close()

        except OSError as os_error:
            if "Bad file descriptor" not in os_error.strerror:
                # TODO: Avoid raise?
                module_logger.error("[IPC] OS error.", exc_info=True, stack_info=True)
                self.lock.release()
                raise os_error

        finally:
            self.lock.release()
