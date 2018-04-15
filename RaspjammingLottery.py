#!/usr/bin/python3
# -*- coding: utf-8 -*

# Copyright (c) 2018 Woergi
# 
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# Twitter-Lib:
# https://pypi.python.org/pypi/twitter
# https://github.com/sixohsix/twitter
# License: MIT

from __future__ import print_function

try:
    import urllib.request as urllib2
    import http.client as httplib
except ImportError:
    import urllib2
    import httplib

try:
    import json
except ImportError:
    import simplejson as json

import sys, uuid
from twitter import Twitter, OAuth, TwitterHTTPError, TwitterStream
from twitter.util import Fail, err
from random import randint
from os.path import expanduser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Timer, Lock
from datetime import datetime, timedelta
import time

# Variables that contains the user credentials to access Twitter API 
AUTH_DATA = { 
    'ACCESS_TOKEN' : '',
    'ACCESS_SECRET' : '',
    'CONSUMER_KEY' : '',
    'CONSUMER_SECRET' : ''
}

TWITTER_AUTH_FILE = expanduser("~") + '/.raspjamming.lottery.twitter.auth'
with open(TWITTER_AUTH_FILE) as authFile:
    for line in authFile:
        line = line.strip().split('=')
        key = line[0].strip()
        if len(key) == 0:
            continue
        AUTH_DATA[key] = line[1].strip()

BLACKLISTED_USER_IDS = [
    #Non-human users:
    90509900, #linuxtage
    #Raspjamming event organisers:
    85056198, #woergi
    265360367, #schusterfredl
    274589676, #m_stroh
    3214578076, #chirndler
]

NO_PLAYER_WON = 42

class Event(object):
    pass


class Observable(object):
    def __init__(self):
        self.callbacks = []
    def subscribe(self, callback):
        self.callbacks.append(callback)
    def _fire(self, **attrs):
        e = Event()
        e.source = self
        for k, v in attrs.items():
            setattr(e, k, v)
        for fn in self.callbacks:
            fn(e)


class Lottery(Observable):
    def __init__(self, playerIds, playerNames):
        super().__init__()
        self.RedeemTimeInSec = 600 # every ~10 min a new winner
        self.playerIds = playerIds
        self.playerNames = playerNames
        self.forfeitPlayers = []

    def _select_winner(self):
        """ Select a winner of all given players. Exclude already played and black listed players """
        if (len(self.playerIds)-len(BLACKLISTED_USER_IDS)-len(self.forfeitPlayers) > 1):
            numTries = 0
            winnerId = self.playerIds[randint(0, len(self.playerIds)-1)]
            while winnerId in BLACKLISTED_USER_IDS \
                    or winnerId in self.forfeitPlayers:
                winnerId = self.playerIds[randint(0, len(self.playerIds)-1)]
                numTries += 1
            print("Winner: " + self.playerNames[winnerId] + " (ID: " + str(winnerId) + ")")
            print("It took " + str(numTries) + " round(s) to select the winner")
            self.forfeitPlayers.append(winnerId)
            return (winnerId, self.playerNames[winnerId])
        else:
            print("No players left -> No winner selected")
            return (NO_PLAYER_WON, "... No players left :(")

    def send_direct_message(self, winnerName, currentValidAuthId):
        """
        Sends a new Direct Message to the specified user from the authenticating user.
        Requires both the user and text parameters and must be a POST. Returns the sent
        message if successful.

        Ok, this endpoint will be deprecated and non-functional on June 19, 2018 ... but I don't care :D
        """
        twitter.direct_messages.new(user=winnerName, text=currentValidAuthId)
        print("Current valid winning auth-id " + currentValidAuthId + " for user " + winnerName)

    def run(self):
        # this is the tick event of the timer, choose a new winner and store it somehow in a global var for the request handler
        (winnerId, winnerName) = self._select_winner()
        currentValidAuthId = str(uuid.uuid4())
        t = time.localtime()
        redeemEndTime = datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec) \
                + timedelta(0, self.RedeemTimeInSec)
        self._fire(winnerId = winnerId, winnerName = winnerName, \
                currentValidAuthId = currentValidAuthId, \
                redeemEndTime = redeemEndTime)
        if winnerId != NO_PLAYER_WON:
            # TODO uncomment direct message sending
            #self.send_direct_message(winnerName, currentValidAuthId)
            Timer(self.RedeemTimeInSec, self.run, ()).start()


class HTTPRequestHandler(BaseHTTPRequestHandler):
    winnerLock = Lock()
    winnerId = 0
    winnerName = ''
    currentValidAuthId = ''

    def set_winner(event):
        with HTTPRequestHandler.winnerLock:
            HTTPRequestHandler.winnerId = getattr(event, 'winnerId', 0)
            HTTPRequestHandler.winnerName = getattr(event, 'winnerName', '')
            HTTPRequestHandler.currentValidAuthId = getattr(event, 'currentValidAuthId', '')
            HTTPRequestHandler.redeemEndTime = getattr(event, 'redeemEndTime', datetime(1,1,1))
            print("Received new winner in HTTPRequestHandler: " + HTTPRequestHandler.winnerName + " (" + str(HTTPRequestHandler.winnerId) + ")")

    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        with HTTPRequestHandler.winnerLock:
            winner = (str(HTTPRequestHandler.winnerId), HTTPRequestHandler.winnerName)
            currentValidAuthId = HTTPRequestHandler.currentValidAuthId
            redeemEndTime = HTTPRequestHandler.redeemEndTime
        print("Request received: " + self.path)
        self._set_headers()
        self.wfile.write(("""
<html>
<header>
    <title>Raspjamming Lottery</title>
    <meta http-equiv="refresh" content="10" />
    <style type='text/css'>
    html, body { 
      height: 100%; 
      background-color: black; 
      color: white; 
    }
    body { 
      display: table; 
      margin: 0 auto; 
    }
    #container { 
      display: table-cell;
      border-collapse: collapse; 
      vertical-align: middle;
      height: 100%; 
      width: 100%; 
      border: 1px solid #000; 
    }
    #layout { 
      display: table-row; 
    }
    #content { 
      display: table-cell;
      text-align: center; 
      vertical-align: middle; 
      font-size: 72;
    }
    </style>
</header>
<body>
    <div id='container'> <div id='layout'> <div id='content'>
    <table id='content'> 
        <tr> <td colspan='2'>The winner is:</td></tr> 
        <tr> <td>Name: </td> <td>""" + winner[1] + """</td> </tr>
        <tr> <td>ID: </td> <td>""" + winner[0] + """</td> </tr>
        <tr> <td colspan='2'>Redemption ends at: """ + redeemEndTime.strftime('%H:%M:%S') + """</td></tr>
        <!-- """ + currentValidAuthId + """ -->
    </table> 
    </div> </div> </div>
</body></html>
        """).encode())

    def do_HEAD(self):
        self._set_headers()


def lookup_portion(twitter, user_ids):
    """Resolve a limited list of user ids to screen names."""
    users = {}
    kwargs = dict(user_id=",".join(map(str, user_ids)), skip_status=1)
    for u in twitter.users.lookup(**kwargs):
        users[int(u['id'])] = u['screen_name']
    return users


def lookup(twitter, user_ids):
    """Resolve an entire list of user ids to screen names."""
    users = {}
    api_limit = 100
    for i in range(0, len(user_ids), api_limit):
        fail = Fail()
        while True:
            try:
                portion = lookup_portion(twitter, user_ids[i:][:api_limit])
            except TwitterError as e:
                if e.e.code == 429:
                    err("Fail: %i API rate limit exceeded" % e.e.code)
                    rls = twitter.application.rate_limit_status()
                    reset = rls.rate_limit_reset
                    reset = time.asctime(time.localtime(reset))
                    delay = int(rls.rate_limit_reset
                                - time.time()) + 5 # avoid race
                    err("Interval limit of %i requests reached, next reset on "
                        "%s: going to sleep for %i secs"
                        % (rls.rate_limit_limit, reset, delay))
                    fail.wait(delay)
                    continue
                elif e.e.code == 502:
                    err("Fail: %i Service currently unavailable, retrying..."
                        % e.e.code)
                else:
                    err("Fail: %s\nRetrying..." % str(e)[:500])
                fail.wait(3)
            except urllib2.URLError as e:
                err("Fail: urllib2.URLError %s - Retrying..." % str(e))
                fail.wait(3)
            except httplib.error as e:
                err("Fail: httplib.error %s - Retrying..." % str(e))
                fail.wait(3)
            except KeyError as e:
                err("Fail: KeyError %s - Retrying..." % str(e))
                fail.wait(3)
            else:
                users.update(portion)
                err("Resolving user ids to screen names: %i/%i"
                    % (len(users), len(user_ids)))
                break
    return users


def follow_portion(twitter, screen_name, cursor=-1, followers=True):
    """Get a portion of followers/following for a user."""
    kwargs = dict(screen_name=screen_name, cursor=cursor)
    if followers:
        t = twitter.followers.ids(**kwargs)
    else: # following
        t = twitter.friends.ids(**kwargs)
    return t['ids'], t['next_cursor']


def follow(twitter, screen_name, followers=True):
    """Get the entire list of followers/following for a user."""
    user_ids = []
    cursor = -1
    fail = Fail()
    while True:
        try:
            portion, cursor = follow_portion(twitter, screen_name, cursor,
                                             followers)
        except TwitterError as e:
            if e.e.code == 401:
                reason = ("follow%s of that user are protected"
                          % ("ers" if followers else "ing"))
                err("Fail: %i Unauthorized (%s)" % (e.e.code, reason))
                break
            elif e.e.code == 429:
                err("Fail: %i API rate limit exceeded" % e.e.code)
                rls = twitter.application.rate_limit_status()
                reset = rls.rate_limit_reset
                reset = time.asctime(time.localtime(reset))
                delay = int(rls.rate_limit_reset
                            - time.time()) + 5 # avoid race
                err("Interval limit of %i requests reached, next reset on %s: "
                    "going to sleep for %i secs" % (rls.rate_limit_limit,
                                                    reset, delay))
                fail.wait(delay)
                continue
            elif e.e.code == 502:
                err("Fail: %i Service currently unavailable, retrying..."
                    % e.e.code)
            else:
                err("Fail: %s\nRetrying..." % str(e)[:500])
            fail.wait(3)
        except urllib2.URLError as e:
            err("Fail: urllib2.URLError %s - Retrying..." % str(e))
            fail.wait(3)
        except httplib.error as e:
            err("Fail: httplib.error %s - Retrying..." % str(e))
            fail.wait(3)
        except KeyError as e:
            err("Fail: KeyError %s - Retrying..." % str(e))
            fail.wait(3)
        else:
            new = -len(user_ids)
            user_ids = list(set(user_ids + portion))
            new += len(user_ids)
            what = "follow%s" % ("ers" if followers else "ing")
            err("Browsing %s %s, new: %i" % (screen_name, what, new))
            if cursor == 0:
                break
            fail = Fail()
    return user_ids


def shutdown_http_server(event):
    if getattr(event, 'winnerId', 0) == NO_PLAYER_WON:
        srv.shutdown()


# Retrieve followers list
oauth = OAuth(AUTH_DATA['ACCESS_TOKEN'],
            AUTH_DATA['ACCESS_SECRET'], 
            AUTH_DATA['CONSUMER_KEY'],
            AUTH_DATA['CONSUMER_SECRET'])
twitter = Twitter(auth=oauth)
user_ids, users = [], {}
try:
    user = sys.argv[1]
    print("Twitter user for lottery: " + user)
    user_ids = follow(twitter, user, True)
    users = lookup(twitter, user_ids)
except KeyboardInterrupt as e:
    err()
    err("Interrupted.")
    raise SystemExit(1)

print("Found users:")
for uid in user_ids:
    try:
        print(str(uid) + "\t" + users[uid])
    except KeyError:
        pass

l = Lottery(user_ids, users)
srv = HTTPServer(('127.0.0.1', 5000), HTTPRequestHandler)
l.subscribe(shutdown_http_server)
l.subscribe(HTTPRequestHandler.set_winner)
l.run()
srv.serve_forever()

# Usage: ./RaspjammingLottery.py Raspjamming

