FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COMFYUI_URL=http://127.0.0.1:8188

WORKDIR /opt/tryon-runtime
COPY runpod_worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY runpod_worker/ ./

CMD ["python", "handler.py"]
