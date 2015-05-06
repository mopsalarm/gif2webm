from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import contextlib
import hashlib
import os
import re
import shutil
import subprocess
import threading
import uuid
from base64 import urlsafe_b64decode

import pathlib
import requests
from concurrent import futures
from flask import abort, jsonify, send_file, Flask


def wrap_in_future(func):
    result = futures.Future()
    try:
        result.set_result(func())
    except Exception as err:
        result.set_exception(err)

    return result


class BlockingPool(object):
    def __init__(self, max_workers):
        self._pool = futures.ThreadPoolExecutor(max_workers)
        self._lock = threading.RLock()
        self._running = {}

    def run(self, key, job):
        with self._lock:
            try:
                return self._running[key]

            except KeyError:
                fast_result = wrap_in_future(job.fast)
                if not fast_result.exception():
                    return fast_result

                # run job on pool
                future = self._pool.submit(job.slow)
                self._running[key] = future
                future.add_done_callback(lambda f: self._remove(key))
                return future

    def _remove(self, key):
        with self._lock:
            self._running.pop(key)

    @property
    def running_count(self):
        with self._lock:
            return len(self._running)


class FileJob(object):
    def __init__(self, target, func):
        self.target = target
        self.func = func

    def fast(self):
        if not self.target.exists():
            raise IOError("file {} not found".format(self.target))

        return self.target

    def slow(self):
        self.func()
        return self.target


class WebmCache(BlockingPool):
    def __init__(self, output_path):
        super(WebmCache, self).__init__(max_workers=2)
        self.output_path = output_path

    def get(self, gif_url):
        """Takes an url to a gif file and returns
        a future containing the path of the webm file, or an
        exception, if the file could not be converted.

        :rtype: futures.Future
        """
        gwid = build_identifier(gif_url)
        webm = self.build_filename(gwid, "webm")
        return self.run(gwid, FileJob(webm, lambda: self._do_convert(gwid, webm, gif_url)))

    def build_filename(self, gwid, extension):
        """:rtype: pathlib.Path"""
        return self.output_path / (gwid + "." + extension)

    def _do_convert(self, gwid, path_webm, gif_url):
        print("got gif {}: {}".format(gwid, gif_url))
        path_gif = self.build_filename(gwid, "gif")

        # if it already exist, just return the file!
        if path_webm.exists():
            return path_webm

        # downloads the gif and stores it into a file
        content = download_file(gif_url)
        print("writing {} byte gif to file".format(len(content)))
        with path_gif.open("wb") as fp:
            fp.write(content)

        try:
            # now convert the gif file
            with gif2webm(path_gif) as temp_path_webm:
                print("renaming webm {} to {}".format(temp_path_webm, path_webm))
                shutil.copy(str(temp_path_webm), str(path_webm))

            # return the path of the webm file
            return path_webm

        finally:
            print("removing downloaded gif file")
            path_gif.unlink()


def build_identifier(url):
    return hashlib.md5(url).hexdigest()


def download_file(url):
    #: :type: requests.Response
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def extract_gif_fps(gif):
    # try to get the frame rate from the gif file
    output = subprocess.check_output(["gifsicle", "-I", str(gif)])
    match = re.search("delay ([0-9.]+)", output)
    if not match:
        return 10.0

    return min(60, max(1, 1 / max(0.01, float(match.group(1)))))


@contextlib.contextmanager
def gif2webm(gif):
    temp = b"/tmp/" + str(uuid.uuid4())
    os.mkdir(temp)
    try:
        print("trying to get fps from gif")
        fps = extract_gif_fps(gif)

        print("converting gif to frames")
        subprocess.check_call(cwd=temp, args=[
            "convert", "-adjoin", "-coalesce", str(gif.absolute()), "frame.%04d.ppm"])

        print("converting frames to webm at {:1.2f}fps".format(fps))
        subprocess.check_call(cwd=temp, args=[
            "avconv", "-r", str(int(fps)), "-i", "frame.%04d.ppm", "-c:v", "libvpx", "-f", "webm",
            "-b:v", "400k", "-qmin", "20", "-qmax", "42", "-an",
            "-y", "video.webm"])

        yield pathlib.Path(temp) / "video.webm"

    finally:
        print("removing temporary data")
        shutil.rmtree(temp)


def make_app():
    app = Flask(__name__)
    cache = WebmCache(pathlib.Path("webm"))

    def _convert(encoded_url):
        gif_url = urlsafe_b64decode(encoded_url.encode("ascii"))
        if not re.match(r"https?://[^/]*pr0gramm\.com/[^?#]+\.gif", gif_url.lower()):
            print("Invalid url")
            raise abort(403)

        webm_path_future = cache.get(gif_url)
        if webm_path_future.exception():
            print("Got exception during conversion: {}".format(webm_path_future.exception()))
            raise abort(500)

        webm_path = webm_path_future.result()
        print("webm found at {}".format(webm_path.absolute()))
        return webm_path


    @app.route('/convert/<encoded_url>')
    def convert(encoded_url):
        _convert(encoded_url)
        return jsonify(path="/webm/{}/video.webm".format(encoded_url))


    @app.route("/webm/<encoded_url>/video.webm")
    def webm(encoded_url):
        webm_path = _convert(encoded_url)
        return send_file(str(webm_path), mimetype="video/webm")


    @app.route("/status")
    def status():
        return jsonify(alive=True, running=cache.running_count)

    return app


if __name__ == '__main__':
    make_app().run(host="0.0.0.0", threaded=True)
