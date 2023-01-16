from functools import cache
import json
import logging
import re
import asyncio
from threading import Timer
from typing import Union

from dggbot import DGGBot, Message, PrivateMessage
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

with open("config.json", "r") as config_json:
    config = json.loads(config_json.read())


cooldown = {"len": 30, "emotes": False}
emotes_bot = DGGBot(config["dgg_auth"], username="Emotes")
emotes_bot.auth = config["dgg_auth"]
emotes_bot.last_message = ""
emotes_bot.blacklist = config["blacklist"]
emotes_bot.admins = config["admins"]

vyneer_phrases = "https://vyneer.me/tools/phrases?ts=1"
regex_check = re.compile(r"^/.*/$")


def save_config():
    to_json = {
        "dgg_auth": emotes_bot.auth,
        "admins": emotes_bot.admins,
        "blacklist": emotes_bot.blacklist,
    }
    with open("config.json", "w") as config_json:
        config_json.write(json.dumps(to_json, indent=2))


def is_regex(text: str) -> Union[re.Pattern, None]:
    if regex_check.search(text):
        try:
            return re.compile(text[1:-1])
        except re.error:
            pass


@cache
def get_phrases():
    r = requests.get(vyneer_phrases)
    data = r.json()["data"]
    regex_phrases = []
    phrases = []
    for item in data:
        if (regex := is_regex(phrase := item["phrase"])) is not None:
            regex_phrases.append(regex)
        else:
            phrases.append(phrase)
    return tuple(phrases), regex_phrases


def check_for_bad_word(text: str) -> bool:
    phrases, regex_phrases = get_phrases()
    return (text in phrases) or any(regex.search(text) for regex in regex_phrases)


def generate_link(msg_author: str, requested_link: str = None):
    def user_response(user):
        response = None
        api_link = f"https://tena.dev/api/users/{user}"
        if user_stats := requests.get(api_link).json():
            link = f"tena.dev/users/{user}"
            if user_stats["emotes"]:
                emotes = list(user_stats["emotes"].keys())[:3]
                response = f"Top 3 emotes: {' '.join(e for e in emotes)} {link}"
            else:
                response = f"Level {user_stats['level']} chatter: {link}"
        return response

    def emote_response(emote):
        response = None
        emotes_api_link = "https://tena.dev/api/emotes"
        emotes = requests.get(emotes_api_link).json().keys()
        if emote in emotes:
            link = f"tena.dev/emotes/{emote}"
            api_link = f"https://tena.dev/api/emotes/{emote}?amount=3"
            top3 = requests.get(api_link).json()
            response = (
                f"Top 3 {emote} posters: {' '.join([n for n in top3.keys()])} {link}"
            )
        return response

    response = None
    if requested_link is not None:
        if arg_is_emote := emote_response(requested_link):
            response = arg_is_emote
        elif arg_is_user := user_response(requested_link):
            response = arg_is_user
    else:
        author_in_db = user_response(msg_author)
        response = author_in_db if author_in_db else "No stats exist for your username"
    return response


def end_cooldown(key):
    cooldown[key] = False


def start_cooldown(key):
    cooldown[key] = Timer(cooldown["len"], end_cooldown, [key])
    cooldown[key].start()


def is_admin(msg: Message):
    return msg.nick in emotes_bot.admins


def not_blacklisted(msg: Message):
    return msg.nick not in emotes_bot.blacklist


@emotes_bot.command(["emotes", "emote"])
@emotes_bot.check(not_blacklisted)
def emotes_command(msg: Message, requested_link: str = None, *_):
    if is_admin(msg) or isinstance(msg, PrivateMessage) or not cooldown["emotes"]:
        if check_for_bad_word(requested_link):
            requested_link = None
        reply = generate_link(msg.nick, requested_link)
        if not isinstance(msg, PrivateMessage):
            if emotes_bot.last_message == reply:
                reply += " ."
            emotes_bot.last_message = reply
            start_cooldown("emotes")
        msg.reply(reply)


@emotes_bot.command(["emotecd"])
@emotes_bot.check(is_admin)
def emotecd_command(msg: Message):
    if msg.data.count(" ") >= 1:
        length = [i for i in msg.data.split(" ") if i][1]
        try:
            length = abs(int(length))
        except ValueError:
            emotes_bot.last_message = reply = "Amount must be an integer"
            msg.reply(reply)
            return
        cooldown["len"] = length
        reply = f"Set cooldown to {length}s"
    else:
        reply = f"Cooldown is currently {cooldown['len']}s"
    emotes_bot.last_message = reply
    msg.reply(reply)


@emotes_bot.command(["blacklist"])
@emotes_bot.check(is_admin)
def blacklist_command(msg: Message):
    if msg.data.count(" ") >= 2:
        arguments = [i for i in msg.data.split(" ") if i]
        mode, user = arguments[1:3]
        if mode == "add" and user not in emotes_bot.blacklist:
            emotes_bot.blacklist.append(user)
            reply = f"Added {user} to blacklist"
        elif mode == "remove" and user in emotes_bot.blacklist:
            emotes_bot.blacklist.remove(user)
            reply = f"Removed {user} from blacklist"
        else:
            reply = "Invalid user"
    else:
        reply = f"Blacklisted users: {' '.join(emotes_bot.blacklist)}"
    save_config()
    emotes_bot.last_message = reply
    msg.reply(reply)


@emotes_bot.command(["updatephrases", "up"])
@emotes_bot.check(is_admin)
def update_phrases_command(msg: Message):
    """Clears the cache for get_phrases() so it will fetch an updated list upon the next call."""
    get_phrases.cache_clear()


@emotes_bot.command(["admin"])
@emotes_bot.check(is_admin)
def admin_command(msg: Message):
    if msg.data.count(" ") >= 2:
        arguments = [i for i in msg.data.split(" ") if i]
        mode, user = arguments[1:3]
        if mode == "add" and user not in emotes_bot.admins:
            emotes_bot.admins.append(user)
            reply = f"Added {user} to admins"
        elif mode == "remove" and user in emotes_bot.admins:
            emotes_bot.admins.remove(user)
            reply = f"Removed {user} from admins"
        else:
            reply = "Invalid user"
    else:
        reply = f"Admin users: {' '.join(emotes_bot.blacklist)}"
    save_config()
    emotes_bot.last_message = reply
    msg.reply(reply)


if __name__ == "__main__":
    logger.info("Starting emotes bot")
    while True:
        emotes_bot.run()
