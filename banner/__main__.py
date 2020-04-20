import argparse
# noinspection PyUnresolvedReferences
import itertools
import json
import select
import ssl
import time
from typing import Dict

import twitchirc

try:
    from . import connections, list_parser
except ImportError:
    import connections
    import list_parser


class Args:
    channel: str
    ban_list_url: str
    auth: str
    list_auth: str
    num_connections: int
    length: int
    sleep_time: float
    connection_wait: float
    is_automated: bool


CUR_UP = '\033[A'
CUR_CLEAR = '\033[K'
CUR_UP_CLEAR = CUR_UP + CUR_CLEAR
BAR_SIZE = 78


def _print_progress_bar(current_number, length, arguments: Args, comment='', log='',
                        message='bans sent!'):
    log = log.rstrip('\n ')
    if arguments.is_automated:
        if log:
            print(f'{{"type": "log", "message": {json.dumps(log)}}}')
        print(json.dumps({"type": "status", "current": current_number, "length": length, "comment": comment}))
        return

    if log:
        print(CUR_CLEAR, log, sep='')

    if length:
        part = current_number / length
        print(f'{CUR_CLEAR}{current_number}/{length} {message} ({part * 100:.2f}%) {comment}')
        bar_filled = part * BAR_SIZE
        print(CUR_CLEAR,
              '[', '=' * round(bar_filled), '>', ' ' * round(BAR_SIZE - bar_filled - 1), ']',
              2 * CUR_UP,
              sep='')
    else:
        print(f'{CUR_CLEAR}{current_number}/? {message}',
              CUR_UP)


def main_from_args(**kwargs):
    args = Args()
    for k, v in kwargs.items():
        setattr(args, k, v)

    return main(args)


def main(args):
    if args.is_automated:
        twitchirc.logging.log = lambda *a, **kwargs: None
        twitchirc.log = lambda *a, **kwargs: None
        print('{"type": "connecting"}')
    # read_connection = twitchirc.Connection('irc.chat.twitch.tv', port=6697, message_cooldown=0, secure=True)
    # read_connection.connect('justinfan123', 'justinfan123')
    # read_connection.cap_reqs(False)
    # read_connection.receive()
    # read_connection.process_messages(100)
    conns = connections.create_connections(args.num_connections, args.auth, args.connection_wait)
    if args.is_automated:
        print('{"type": "connected"}')
    else:
        _print_progress_bar(0, 1, args, 'Connected', log='Connected')
    if args.list_auth:
        headers = {
            'Authorization': args.list_auth
        }
    else:
        headers = {}
    channel = args.channel
    current_connection_number = 0
    if not args.is_automated:
        print()
        print()
    conn_messages = {i: [] for i in range(len(conns))}
    start_time = time.time()
    next_read_connections = {
        i: time.monotonic() for i in range(len(conns))
    }
    for num, ban in enumerate(list_parser.BanListIterator(args.ban_list_url, request_headers=headers)):
        if current_connection_number >= len(conns):
            current_connection_number = 0
        conn = conns[current_connection_number]
        try:
            conn.socket.send(f'PRIVMSG #{channel} :{ban}\r\n'.encode())
        except (BrokenPipeError, ssl.SSLZeroReturnError):
            conns[current_connection_number] = connections.create_connections(1, args.auth,
                                                                              args.connection_wait)
            conn = conns[current_connection_number]
            conn.socket.send(f'PRIVMSG #{channel} :{ban}\r\n'.encode())

        if num % 50 == 0 and not args.enable_progress_reading:
            _print_progress_bar(num, args.length, args)

        if args.enable_progress_reading:
            if next_read_connections[current_connection_number] > time.monotonic():
                continue
            next_read_connections[current_connection_number] = time.monotonic() + 1

            while 1:
                read, _, _ = select.select([conn.socket], [], [], 0)
                if not read:
                    break
                o = conn.receive()
                if o == 'RECONNECT':
                    try:
                        conn.disconnect()
                    except BrokenPipeError:
                        pass
                    conns[current_connection_number] = connections.create_connections(1, args.auth,
                                                                                      args.connection_wait)

            msgs = conn.process_messages(10_000)
            _print_progress_bar(num, args.length, args,
                                f'Received data from #{current_connection_number}',
                                log='\n'.join([repr(i) for i in msgs]))

            conn_messages[current_connection_number].extend(msgs)
        current_connection_number += 1
        time.sleep(args.sleep_time)

    num_bans = num
    time.sleep(0.5)
    last_collected = -1
    for num, conn in enumerate(conns):
        _print_progress_bar(num, len(conns), args, comment='Collecting messages',
                            log=(
                                '' if last_collected == -1 else f'Collected {last_collected} messages from #{num - 1}\n'
                            ),
                            message=f'Receiving from #{num}')
        last_collected = 0
        while 1:
            read, _, _ = select.select([conn.socket], [], [], 0.5)
            if not read:
                break
            o = conn.receive()
            if o == 'RECONNECT':
                break

            data = conn.process_messages(10_000)
            last_collected += len(data)
            conn_messages[num].extend(data)

    end_time = time.time()
    _print_progress_bar(num_bans, num_bans, args, comment='Finished!',
                        log=f'Operation took {end_time - start_time:.2f}s')
    _print_progress_bar(num_bans, num_bans, args, comment='Finished!',
                        log=f'Speed: {num_bans / (end_time - start_time)}')

    bans: Dict[str, bool] = {
        # 'username': True,
        # 'username2': False
    }
    for msg in itertools.chain.from_iterable(conn_messages.values()):
        if isinstance(msg, twitchirc.Message) and f'NOTICE #{channel}' in msg.raw_data:
            tags = {
                i.split('=')[0]: i.split('=')[1] for i in msg.raw_data.split(' ')[0].lstrip('@').split(';')
            }
            if tags['msg-id'] in ['ban_success', 'already_banned']:
                username = msg.raw_data.split(' ')[4].lstrip(':')
                if username in bans:
                    continue
                bans[username] = 'ban_success' == tags['msg-id']

    _print_progress_bar(num_bans, num_bans, args, comment='',
                        log=f'Sent {num_bans} commands, got {len(bans)} responses')
    new_bans = sum(bans.values())
    _print_progress_bar(num_bans, num_bans, args, comment='',
                        log=f'New bans: {new_bans}')

    _print_progress_bar(num_bans, num_bans, args, comment='',
                        log=f'Percentage of new bans from responses: {new_bans / len(bans) * 100:.2f}')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('channel')
    p.add_argument('ban_list_url')
    p.add_argument('-a', '--auth', dest='auth', required=True)
    p.add_argument('-A', '--list-auth', dest='list_auth')
    p.add_argument('-n', '--number', dest='num_connections', default=5, type=int)
    p.add_argument('-l', '--length', dest='length', default=10_000, type=int)
    p.add_argument('-T', '--sleep-time', dest='sleep_time', default=0.03, type=float)
    p.add_argument('-c', '--connection-wait', dest='connection_wait', default=1.0, type=float)
    p.add_argument('-p', '--json', dest='is_automated', action='store_true')
    p.add_argument('-nP', '--no-progress', dest='enable_progress_reading', action='store_false')
    aargs = p.parse_args(namespace=Args())

    main(aargs)
