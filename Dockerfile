FROM gliderlabs/python-runtime:3.4
MAINTAINER Mopsalarm

RUN apk --update add ffmpeg coreutils

# videos are placed at /usr/src/app/webm
CMD PYTHONPATH=/app /env/bin/python -m bottle -s wsgiref -b 0.0.0.0:5000 gif2webm

EXPOSE 5000
