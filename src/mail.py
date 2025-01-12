import mimetypes
import os
import smtplib
from email import encoders
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class Content:
    filename: str
    content: str


class Mail:
    def __init__(self, addr_from, password, addr_to, subject, text):
        self.addr_from = addr_from
        self.password = password
        msg = MIMEMultipart()
        msg["From"] = self.addr_from
        msg["To"] = addr_to
        msg["Subject"] = subject

        msg.attach(MIMEText(text, "plain"))
        self.msg = msg

    def add_attachment(self, path=None, content: Content | None = None):
        assert bool(path) ^ bool(content)
        if content:
            file = MIMEText(content.content)
            self._add_attachment(file, content.filename)
        if os.path.isfile(path):
            self._attach_file(path)
        elif os.path.isdir(path):
            dir = os.listdir(path)
            for file in dir:
                self._attach_file(os.path.join(path, file))
        else:
            assert False, f"{path} is neither file nor directory"
        return self

    def _attach_file(self, filepath):
        filename = os.path.basename(filepath)
        ctype, encoding = mimetypes.guess_type(filepath)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        if maintype == "text":
            with open(filepath) as fp:
                file = MIMEText(fp.read(), _subtype=subtype)
        elif maintype == "image":
            with open(filepath, "rb") as fp:
                file = MIMEImage(fp.read(), _subtype=subtype)
        elif maintype == "audio":
            with open(filepath, "rb") as fp:
                file = MIMEAudio(fp.read(), _subtype=subtype)
        else:
            with open(filepath, "rb") as fp:
                file = MIMEBase(maintype, subtype)
                file.set_payload(fp.read())
                encoders.encode_base64(file)
        self._add_attachment(file, filename)

    def _add_attachment(self, file, filename):
        file.add_header("Content-Disposition", "attachment", filename=filename)
        self.msg.attach(file)

    def send(self):
        server = smtplib.SMTP_SSL("smtp.yandex.ru", 465)
        server.login(self.addr_from, self.password)
        server.send_message(self.msg)
        server.quit()
