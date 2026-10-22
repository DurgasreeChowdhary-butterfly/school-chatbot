"""A tiny fake SMTP server for tests. It speaks just enough SMTP for Python's smtplib, keeps every
message in memory, and can be told to refuse the next few messages. Nothing leaves the computer."""
import socketserver
import threading
from email import message_from_bytes, policy


class FakeSMTPServer:
    def __init__(self):
        self.messages = []   # [{"to": [...], "subject": ..., "body": ...}]
        self.fail_next = 0   # refuse this many messages with a temporary error
        server = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                rcpt = []
                self.reply("220 fake smtp ready")
                while line := self.rfile.readline():
                    cmd = line.decode("utf-8", "replace").strip()
                    verb = cmd.split(" ")[0].upper()
                    if verb in ("EHLO", "HELO"):
                        self.reply("250 fake")
                    elif verb == "MAIL":
                        rcpt = []
                        self.reply("250 OK")
                    elif verb == "RCPT":
                        rcpt.append(cmd.split(":", 1)[1].strip(" <>"))
                        self.reply("250 OK")
                    elif verb == "DATA":
                        self.reply("354 send it")
                        data = b""
                        while (chunk := self.rfile.readline()) not in (b".\r\n", b""):
                            data += chunk
                        if server.fail_next > 0:
                            server.fail_next -= 1
                            self.reply("451 try again later")
                            continue
                        msg = message_from_bytes(data, policy=policy.default)
                        server.messages.append({"to": rcpt, "subject": str(msg["Subject"]),
                                                "body": msg.get_content()})
                        self.reply("250 queued")
                    elif verb == "QUIT":
                        self.reply("221 bye")
                        return
                    else:
                        self.reply("250 OK")

            def reply(self, text):
                self.wfile.write((text + "\r\n").encode())

        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
