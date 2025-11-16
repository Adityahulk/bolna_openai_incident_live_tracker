FROM python:3.11-alpine
RUN apk add --no-cache ca-certificates && update-ca-certificates
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY status_watcher.py /app/status_watcher.py
VOLUME /data
CMD ["sh","-c","python /app/status_watcher.py --bootstrap-log | tee -a /data/openai-status.log"]