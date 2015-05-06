from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from base64 import urlsafe_b64decode

import hashlib
import os
import subprocess
import contextlib
import threading
import traceback
import uuid
import shutil
import re

from flask import abort, jsonify, send_file, Flask
import pathlib
import requests
from concurrent import futures


class WebmCache(object):
    def __init__(self, output_path):
        self.output_path = output_path
        self.pool = futures.ThreadPoolExecutor(max_workers=4)
        self.lock = threading.RLock()
        self.cache = {}

    def get(self, gif_url):
        """Takes an url to a gif file and returns
        a future containing the path of the webm file, or an
        exception, if the file could not be converted.

        :rtype: futures.Future
        """
        gwid = build_identifier(gif_url)
        with self.lock:
            if gwid in self.cache:
                return self.cache[gwid]

            future = self.pool.submit(self._do_convert, gwid, gif_url)
            self.cache[gwid] = future
            return future

    def build_filename(self, gwid, extension):
        """:rtype: pathlib.Path"""
        return self.output_path / (gwid + "." + extension)

    def _do_convert(self, gwid, gif_url):
        print("got gif {}: {}".format(gwid, gif_url))
        path_gif = self.build_filename(gwid, "gif")
        path_webm = self.build_filename(gwid, "webm")

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
    return jsonify(alive=True)


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


# gifsicle -I 3769e63a9da3704d.gif
# disposal asis delay 0.04s
# convert -adjoin -coalesce 3769e63a9da3704d.gif frame.%04d.ppm
# avconv -r 25 -i frame.%04d.ppm -c:v libvpx -f webm -b:v 400k -qmin 20 -qmax 42 -an -y output.webm

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, use_reloader=False, threaded=True)
