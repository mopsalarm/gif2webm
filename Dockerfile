from python:2-onbuild
MAINTAINER Mopsalarm

ADD http://johnvansickle.com/ffmpeg/releases/ffmpeg-release-64bit-static.tar.xz /tmp/ffmpeg.tar.xz
RUN xz -d /tmp/ffmpeg.tar.xz && tar -xC/usr/bin -f /tmp/ffmpeg.tar

# videos are placed at /usr/src/app/webm
CMD python gif2webm.py

EXPOSE 8080

