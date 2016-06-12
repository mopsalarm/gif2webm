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


datadog.initialize()
stats = datadog.ThreadStats()
stats.start()


class VideoNotConvertedError(Exception):
    pass


def metric_name(suffix):
    return "pr0gramm.gif2vid.v2.%s" % suffix


@stats.timed(metric_name("convert"))
def make_video(url, target):
    temp_gif = tempfile.mktemp(suffix=".gif")
    temp_output = tempfile.mktemp(suffix=".mp4")
    try:
        # download file
        subprocess.check_call(["timeout", "-s", "KILL", "5s",
                               "curl", "-o", temp_gif, url])

        ffprobe_output = subprocess.check_output(
            ["timeout", "-s", "KILL", "5s", "ffprobe", "-show_packets", temp_gif])

        frame_count = ffprobe_output.count(b"codec_type=video")
        if frame_count <= 5:
            return False

        # and convert
        subprocess.check_call(["timeout", "-s", "KILL", "30s",
                               "ffmpeg", "-y", "-i", temp_gif, "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                               "-codec:v", "libx264", "-preset", "medium", "-b:v", "350k", "-an",
                               "-profile:v", "baseline", "-level", "3.0", "-pix_fmt", "yuv420p",
                               "-qmin", "20", "-qmax", "42", temp_output])

        # and move to target
        shutil.copy(temp_output, str(target))
        return True
    except:
        stats.increment(metric_name("error"))
        raise

    finally:
        for temp in temp_gif, temp_output:
            try:
                pass
                # os.unlink(temp)
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
                future = self.pool.submit(self._convert_in_background, url)
                self.jobs[url] = future
                return future

    def _convert_in_background(self, url):
        target = self.images / re.sub("[^a-z0-9]", "_", url.lower())
        if not target.exists() or not target.stat().st_size:
            if not make_video(url, target):
                raise VideoNotConvertedError()

        return target


converter = Converter()


def convert(url):
    url = base64.urlsafe_b64decode(url.encode("ascii")).strip().decode("utf8")
    if not re.match("^https?://[^/]*pr0gramm.com/.*$", url):
        return bottle.abort(403)

    # use only http
    url = url.replace("https://", "http://")
    return str(converter.video(url).result())


@bottle.get("/convert/:url")
def convert_route(url):
    convert(url)
    bottle.response.add_header("Cache-Control", "max-age=31556926")
    return dict(path="/webm/{}/video.webm".format(url))


@bottle.get("/webm/:url/video.webm")
def video_route(url):
    stats.increment(metric_name("request"))

    response = bottle.static_file(convert(url), os.path.abspath("."), mimetype="video/mp4")
    response.set_header("Cache-Control", "max-age=31556926")
    return response


@bottle.get("/status")
def status():
    return dict(alive=True)
