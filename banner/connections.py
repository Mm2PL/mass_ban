import time

import twitchirc


def create_connections(how_many: int, auth: str, wait_time: float):
    output = []
    for _ in range(how_many):
        conn = twitchirc.Connection('irc.chat.twitch.tv', 6697, message_cooldown=0, secure=True)
        conn.connect('doesnt_matter', ('oauth:' + auth) if not auth.startswith('oauth:') else auth)
        conn.cap_reqs(False)
        conn.receive()
        output.append(conn)
        time.sleep(wait_time)
    return output
