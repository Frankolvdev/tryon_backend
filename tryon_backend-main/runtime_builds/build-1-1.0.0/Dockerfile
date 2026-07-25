FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git curl ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /opt/ComfyUI
RUN pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision torchaudio
RUN pip install -r /opt/ComfyUI/requirements.txt
COPY runpod_worker /opt/tryon/runpod_worker
WORKDIR /opt/tryon/runpod_worker
RUN pip install -r requirements.txt
COPY runtime-builder/entrypoint.sh /opt/tryon/entrypoint.sh
RUN chmod +x /opt/tryon/entrypoint.sh
ENTRYPOINT ["/opt/tryon/entrypoint.sh"]
