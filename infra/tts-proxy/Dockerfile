# Minimal transcoding proxy: Python standard library + Debian ffmpeg.
FROM python:3.13-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY server.py /opt/tts-proxy/server.py
USER 65534:65534
EXPOSE 8080
CMD ["python", "-u", "/opt/tts-proxy/server.py"]
