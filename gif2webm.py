from __future__ import division
from __future__ import unicode_literals

import gevent.monkey
gevent.monkey.patch_all(subprocess=True, Event=True)

import os
import shutil
import tempfile
import subprocess
import threading
import base64
import re

import bottle
import datadog
import pathlib
from concurrent.futures import ThreadPoolExecutor


# initialize datadog
datadog.initialize()
stats = datadog.ThreadStats()
stats.start()


def metric_name(suffix):
    return "pr0gramm.gif2vid.v2.%s" % suffix


@stats.timed(metric_name("convert"))
def make_video(url, target):
    temp_gif = tempfile.mktemp(suffix=".gif")
    temp_output = tempfile.mktemp(suffix=".webm")
    try:
        # download file
        subprocess.check_call(["curl", "-o", temp_gif, url])

        # and convert
        subprocess.check_call(["ffmpeg", "-i", temp_gif, "-c:v", "libvpx", "-f", "webm",
                               "-b:v", "400k", "-qmin", "20", "-qmax", "42", "-an",
                               "-y", temp_output])

        # and move to target
        shutil.copy(temp_output, str(target))

    finally:
        for temp in temp_gif, temp_output:
            try:
                os.unlink(temp)
            except OSError:
                pass


class Converter(object):
    def __init__(self):
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(2)
        self.jobs = {}

        self.images = pathlib.Path("webm")
        if not self.images.exists():
            self.images.mkdir()

    def video(self, url):
        with self.lock:
            try:
                return self.jobs[url]
            except KeyError:
                future = self.pool.submit(self._video, url)
                self.jobs[url] = future
                return future

    def _video(self, url):
        target = self.images / re.sub("[^a-z0-9]", "_", url.lower())
        if not target.exists() or not target.stat().st_size:
            make_video(url, target)

        return target


converter = Converter()


def convert(url):
    url = base64.urlsafe_b64decode(url.encode("ascii")).strip()
    if not re.match("^https?://[^/]*pr0gramm.com/.*$", url):
        return bottle.abort(403)

    # use only http
    url = url.replace("https://", "http://")
    return str(converter.video(url).result())


@bottle.get("/convert/:url")
def convert_route(url):
    convert(url)
    bottle.response.add_header(b"Cache-Control", b"max-age=31556926")
    return dict(path="/webm/{}/video.webm".format(url))


@bottle.get("/webm/:url/video.webm")
def video_route(url):
    stats.increment(metric_name("request"))

    response = bottle.static_file(convert(url), os.path.abspath("."), mimetype="video/webm")
    response.set_header(b"Cache-Control", b"max-age=31556926")
    return response


@bottle.get("/status")
def status():
    return dict(alive=True)


if __name__ == "__main__":
    bottle.run(server="gevent", host="0.0.0.0", port=5000, debug=True)
