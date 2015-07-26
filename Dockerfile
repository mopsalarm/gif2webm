FROM gliderlabs/python-runtime:3.4
MAINTAINER Mopsalarm

RUN curl http://johnvansickle.com/ffmpeg/releases/ffmpeg-release-64bit-static.tar.xz \
    | xz -d \
    | tar xC /usr/bin --strip-components=1 \
    && rm /usr/bin/ffserver \
    && rm /usr/bin/ffprobe \
    && rm /usr/bin/ffmpeg-10bit

# videos are placed at /usr/src/app/webm
CMD PYTHONPATH=/app /env/bin/python -m bottle -s wsgiref -b 0.0.0.0:5000 gif2webm

EXPOSE 5000
