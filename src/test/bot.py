import abc
import collections
import dataclasses
import typing

@dataclasses.dataclass
class Chat:
    id: int

@dataclasses.dataclass
class File:
    file_id: str

@dataclasses.dataclass
class FileInfo:
    file_id: str
    _content: bytes
    file_size: int = 0
    file_path: str = ''

    def __post_init__(self):
        self.file_size = len(self._content)
        self.file_path = 'file/' + self.file_id

@dataclasses.dataclass
class Message:
    id: int
    chat: Chat
    text: typing.Optional[str] = None
    reply_to_message: typing.Optional["Message"] = None
    document: File | None = None

class MockTelebotObserver:
    @abc.abstractmethod
    def on_message(self, sent_by_bot: bool, message: Message):
        pass

class MockTelebot:
    def __init__(self):
        self.handlers = []
        self.chats = collections.defaultdict(list)
        self.full_chats = collections.defaultdict(list)
        self.bot = None
        self.message_id = 0
        self.files = {}
        self._observers = []

    def add_observer(self, observer: MockTelebotObserver):
        self._observers.append(observer)

    def message_handler(self, commands=None, func=None, content_types=None):
        content_types = content_types or []
        return lambda handler: self.handlers.append((commands, func, content_types, handler))

    def send_message(self, chat_id, text):
        self.chats[chat_id].append(text)
        self.message_id += 1
        message = Message(self.message_id, Chat(chat_id), text=text)
        self.full_chats[chat_id].append(message)
        self._notify(lambda o: o.on_message(True, message))
        return message

    def infinity_polling(self):
        pass

    def stop_bot(self):
        pass

    def user_message(self, chat_id, text=None, reply_to=None, file=None):
        for commands, func, content_types, handler in self.handlers:
            message = Message(-1-len(self.chats[chat_id]), Chat(chat_id), reply_to_message=reply_to, document=file)
            message_content_types = []
            if message.document:
                message_content_types.append('document')
            if content_types != message_content_types:
                continue
            if commands and text in commands:
                handler(message)
            elif func and func(message):
                handler(message)
        self._notify(lambda o: o.on_message(False, message))
        return message

    def add_file(self, file_id: str, content: bytes):
        self.files[file_id] = FileInfo(file_id, content)

    def get_file(self, file_id: str):
        return self.files[file_id]

    def download_file(self, file_path: str):
        assert file_path.startswith('file/')
        file_id = file_path[len('file/'):]
        return self.files[file_id]._content

    def _notify(self, f):
        for o in self._observers:
            f(o)