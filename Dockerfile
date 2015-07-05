from python:2-onbuild
MAINTAINER Mopsalarm

ADD http://johnvansickle.com/ffmpeg/releases/ffmpeg-release-64bit-static.tar.xz /tmp/ffmpeg.tar.xz
RUN xz -d /tmp/ffmpeg.tar.xz && tar -xC/usr/bin -f /tmp/ffmpeg.tar --strip-components 1

# videos are placed at /usr/src/app/webm
CMD python -m bottle -s wsgiref -b 0.0.0.0:8080 gif2webm

EXPOSE 5000

