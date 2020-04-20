import typing

import requests


def parse_line(line: str) -> typing.Optional[typing.Tuple[str, typing.Optional[str]]]:
    """
    Parse a line from ban list.
    parse_line(line: str) -> (username, reason) || (username, None) || None

    Returns a tuple of a string and optional reason or None.

    If the line starts with '#', '//', ';' or '%%' it will be ignored.
    If the line starts with '.' or '/' it will be parsed like a command
    If the line doesn't match any of these cases it will be returned as the username
    """
    if line.startswith(('#', '//', ';', '%%')):
        return None
    if line.startswith(('.', '/')):
        command = line.replace('.', '', 1).replace('/', '', 1)
        if command.startswith('ban'):
            argv = command.split(' ', 2)
            # .ban user reason
            if len(argv) == 2:  # no reason
                return argv[1], None
            elif len(argv) == 3:  # reason provided
                return argv[1], argv[2]
            else:
                return None
        elif command.startswith('timeout'):
            argv = command.split(' ', 3)
            # .timeout user length reason
            if len(argv) == 3:
                return argv[1], None
            elif len(argv) == 4:  # reason provided
                return argv[1], argv[3]
            else:
                return None
    else:
        return line, None


def format_ban(username: str, reason: typing.Optional[str]) -> str:
    if reason:
        return f'.ban {username} {reason}'
    else:
        return f'.ban {username} Mass banned.'


class BanListIterator:
    def __init__(self, url: str, request_headers: typing.Optional[dict] = None,
                 request_params: typing.Optional[dict] = None):
        self.url = url
        self.request = requests.request('get', url, headers=request_headers, params=request_params, stream=True)
        self.request_iterator = self.request.iter_lines()

    def __iter__(self):
        return self

    def __next__(self):
        ban_data = None
        while ban_data is None:
            ban_data = parse_line(next(self.request_iterator).decode())
        return format_ban(*ban_data)
