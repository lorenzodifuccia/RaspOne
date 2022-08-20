import logging
import threading
import subprocess

from src import DEFAULT_NAME

module_logger = logging.getLogger(DEFAULT_NAME + ".server")


class ServerExecutionException(Exception):
    """Exception raised by the server in case of error."""


class Server:
    def __init__(self):
        self.lock = threading.Lock()
        self.running_processes = []

        self.default_error_message = "Error during server `exec`. See internal log for further details."

    def exec(self, args, shell=False, env=None):
        self.lock.acquire()
        try:
            proc = subprocess.Popen(args=args,
                                    shell=shell, env=env, universal_newlines=True,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            self.running_processes.append(proc)

        except (subprocess.SubprocessError, subprocess.CalledProcessError, OSError, Exception) as exec_error:
            module_logger.error("[SERVER] Subprocess error.", exc_info=True, stack_info=True)
            raise ServerExecutionException(exec_error)

        finally:
            self.lock.release()

        return proc

    def run(self, args, shell=False, env=None, stdin_input=None, timeout=5):
        try:
            module_logger.info("[SERVER] Executing: '%s'" % str(args))
            proc = self.exec(args, shell, env)
        except ServerExecutionException:
            return False, None, None

        stdout, stderr = proc.communicate(input=stdin_input, timeout=timeout)

        return proc, stdout, stderr

    def is_process_running(self, process):
        proc, stdout, stderr = self.run(("pgrep", process))
        if not proc:
            return False, self.default_error_message

        elif len(stderr):
            return False, stderr

        elif len(stdout):
            return True, None

        else:
            return False, None

    def kill_proc(self, proc):
        self.lock.acquire()
        proc.terminate()
        if proc in self.running_processes:
            self.running_processes.remove(self.running_processes.index(proc))

        self.lock.release()

    def kill(self):
        self.lock.acquire()
        for _ in range(len(self.running_processes)):
            p = self.running_processes.pop()
            p.terminate()

        self.lock.release()
