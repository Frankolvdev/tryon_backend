FROM python:3.12-alpine
WORKDIR /app
COPY worker.py /app/worker.py
EXPOSE 8765
CMD ["python", "-u", "/app/worker.py"]
