#!/usr/bin/env python3
"""
Jarvis IRC Wrapper.

This module contains irc-specific functionality such as autocomplete, and
connects jarvis functions to allow them to be called from irc.
"""


###############################################################################
# Module Imports
###############################################################################

import arrow
import functools
import sopel
import textwrap

from jarvis import autoban, core, notes, scp, tools, websearch, images

###############################################################################
# Core Wrapper Functions
###############################################################################


@sopel.module.commands('\w+')
def autocomplete(bot, tr):
    """Automatically complete partially entered commands."""
    funcs = [f for group in bot._callables.values() for f in group.values()]
    funcs = {f for l in funcs for f in l if hasattr(f, 'commands')}
    partial = tr.group(1)
    if any(partial in f.commands for f in funcs):
        return
    funcs = [
        f for f in funcs if any(c.startswith(partial) for c in f.commands)]
    if not funcs:
        return
    if len(funcs) > 1:
        send(
            bot,
            tools.choose_input([f.commands[0] for f in funcs]).format(None))
    else:
        wrapper = bot.SopelWrapper(bot, tr)
        bot.call(funcs[0], wrapper, tr)


def send(bot, text, private=False, notice=False):
    """Send irc message."""
    tr = bot._trigger
    notes.Message.create(
        user=bot.config.core.nick,
        channel=tr.sender,
        time=arrow.utcnow().timestamp,
        text=text)
    mode = 'NOTICE' if notice else 'PRIVMSG'
    recipient = tr.nick if private or notice else tr.sender
    try:
        bot.sending.acquire()
        for line in textwrap.wrap(text, width=420):
            bot.write((mode, recipient), line)
    finally:
        bot.sending.release()


def privileges(bot, nick):
    channels = bot.privileges.items()
    return {str(k): v[nick] for k, v in channels if nick in v}


def wrapper(fn, group, *args, **kwargs):

    def inner(bot, tr):
        inp = core.Inp(
            tr.group(group),
            tr.nick,
            tr.sender,
            functools.partial(send, bot),
            functools.partial(privileges, bot, tr.nick))
        return fn(inp, *args, **kwargs)
    return inner


def command(trigger, fn, *args, **kwargs):
    inner = wrapper(fn, 2, *args, **kwargs)
    inner = sopel.module.commands(*trigger.split())(inner)
    count = sum(1 for i in globals() if i.startswith(fn.__name__))
    globals()['{}_{}'.format(fn.__name__, count + 1)] = inner


def rule(trigger, fn, *args, priority='medium', **kwargs):
    inner = wrapper(fn, 1, *args, **kwargs)
    inner = sopel.module.rule(trigger)(inner)
    inner = sopel.module.priority(priority)(inner)
    count = sum(1 for i in globals() if i.startswith(fn.__name__))
    globals()['{}_{}'.format(fn.__name__, count + 1)] = inner


###############################################################################
# Notes
###############################################################################


command('tell', notes.tell)
command('showtells st', notes.show_tells)
command('outbound', notes.outbound)
command('seen', notes.seen)
command('quote', notes.quote)
command('remember', notes.save_memo)
command('topic', notes.topic)
command('alert', notes.alert)
command('backport', notes.backport)

rule(r'(.*)', notes.logevent, priority='low')
rule(r'(.*)', notes.get_tells, priority='low')
rule(r'(.*)', notes.get_alerts, priority='low')
rule(r'(\?[^\s]+)\s*$', notes.load_memo)


###############################################################################
# scp
###############################################################################


@sopel.module.interval(3600)
def refresh(bot):
    core.refresh()


command('search s', scp.search)
command('tale', scp.tale)
command('tags', scp.tags)
command('wandererslibrary wl', scp.wanderers_library)
command('author', scp.author)
command('ad', scp.author_details)
command('lastcreated lc', scp.last_created)
command('unused', scp.unused)
command('random', scp.random)
command('errors', scp.errors)
command('staff', scp.staff)

rule(r'(?i).*http[s]?://www\.scp-wiki\.net/([^/\s]+)(?:\s|$)', scp.name_lookup)
rule(r'(?i)^(scp-[\d]+(?:-[\w]+)?)\s*$', scp.name_lookup)
rule(r'(?i).*!(scp-\d+(?:-[\w]+)?)', scp.name_lookup)


###############################################################################
# Tools
###############################################################################


command('showmore sm', tools.showmore)
command('choose', tools.choose)
command('roll dice', tools.roll)
command('user', tools.user)
command('zyn', tools.zyn)
command('help', tools.help)

command('notdelivered nd', tools.deprecate, '!outbound count')
command('purgetells', tools.deprecate, '!outbound purge')
command('restrict', tools.deprecate, '!topic res <topic>')
command('unrestrict', tools.deprecate, '!topic unres <topic>')
command('subscribe', tools.deprecate, '!topic sub <topic>')
command('unsubscribe', tools.deprecate, '!topic unsub <topic>')
command('firstseen', tools.deprecate, '!seen -f <name>')


rule(r'(?i)(^(?:[+-]?[0-9]*d(?:[0-9]+|f))+(?:[+-][0-9]+)?$)', tools.roll)
rule(r'(?i)(^(?=.*\b$nickname)(?=.*\bhugs?\b).*)', tools.get_hugs)

###############################################################################
# Websearch
###############################################################################


command('google g', websearch.google_search)
command('gis', websearch.google_image_search)
command('youtube yt', websearch.youtube)
command('wikipedia w', websearch.wikipedia)
command('definition define dictionary', websearch.dictionary)
command('urbandictionary', websearch.urbandictionary)

rule(r'.*youtube\.com/watch\?v=([-_a-z0-9]+)', websearch.youtube_lookup)
rule(r'.*youtu\.be/([-_a-z0-9]+)', websearch.youtube_lookup)


###############################################################################
# Images
###############################################################################

command('images img', images.images)

###############################################################################
# Autoban
###############################################################################


command('updatebans', autoban.update_bans)


@sopel.module.event('JOIN')
@sopel.module.rule('.*')
def ban_on_join(bot, tr):
    if tr.sender != '#site19':
        return

    def kick(message):
        bot.write(['KICK', tr.sender, tr.nick], message)

    def ban(target, enable):
        bot.write(['MODE', tr.sender, '+b' if enable else '-b', target])

    send_ = functools.partial(send, bot)

    if not autoban.ban_evasion(tr.nick, tr.host, kick, ban, send_):
        autoban.offensive_username(tr.nick, tr.host, kick, ban, send_)
