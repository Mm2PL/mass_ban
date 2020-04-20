import argparse
# noinspection PyUnresolvedReferences
import json
import select
import time

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
    read_connection = twitchirc.Connection('irc.chat.twitch.tv', port=6697, message_cooldown=0, secure=True)
    read_connection.connect('justinfan123', 'justinfan123')
    read_connection.cap_reqs(False)
    read_connection.receive()
    read_connection.process_messages(100)
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
    for num, ban in enumerate(list_parser.BanListIterator(args.ban_list_url, request_headers=headers)):
        if current_connection_number >= len(conns):
            current_connection_number = 0
        # print(ban)
        conn = conns[current_connection_number]
        try:
            conn.socket.send(f'PRIVMSG #{channel} :{ban}\r\n'.encode())
        except BrokenPipeError:
            conns[current_connection_number] = connections.create_connections(1, args.auth,
                                                                              args.connection_wait)
            conn = conns[current_connection_number]
            conn.socket.send(f'PRIVMSG #{channel} :{ban}\r\n'.encode())

        current_connection_number += 1

        if num % 50 == 0:
            _print_progress_bar(num, args.length, args)

        if num % (30 * current_connection_number) == 0:
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

            conn_messages[current_connection_number] = msgs
        time.sleep(args.sleep_time)
    num_bans = num
    for num, conn in enumerate(conns + [read_connection]):
        _print_progress_bar(num, len(conns), args, comment='Collecting messages', log=f'Receiving from #{num}',
                            message='')

        while 1:
            read, _, _ = select.select([conn.socket], [], [], 0.5)
            if not read:
                break
            o = conn.receive()
            if o == 'RECONNECT':
                break
            conn_messages[num] = conn.process_messages(10_000)
    print(conn_messages)
    end_time = time.time()
    print(start_time, end_time)
    print(end_time - start_time)
    _print_progress_bar(num_bans, num_bans, args, comment='Finished!',
                        log=f'Operation took {end_time - start_time:.2f}s')
    _print_progress_bar(num_bans, num_bans, args, comment='Finished!',
                        log=f'Speed: {num_bans / (end_time - start_time)}')


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
    aargs = p.parse_args(namespace=Args())

    main(aargs)
