from python:2-onbuild
MAINTAINER Mopsalarm

RUN apt-get update && apt-get install -y --force-yes libav-tools imagemagick gifsicle && apt-get clean

# videos are placed at /usr/src/app/webm
CMD python gif2webm.py

EXPOSE 5000

