FROM nvidia/cuda:12.8-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git curl ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/comfyanonymous/ComfyUI /opt/ComfyUI
RUN git -C /opt/ComfyUI checkout 3dd10a59c00248d00f0cb0ab794ff1bb9fb00a5f
RUN pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision torchaudio
RUN pip install -r /opt/ComfyUI/requirements.txt
RUN git clone https://github.com/DemonGatanjieu/Anomalous_Model_Browser /opt/ComfyUI/custom_nodes/Anomalous_Model_Browser
RUN git -C /opt/ComfyUI/custom_nodes/Anomalous_Model_Browser checkout cf2866dc1094e5f783f2fe77a719429b1d8d6f75
RUN git clone https://github.com/ltdrdata/ComfyUI-Manager /opt/ComfyUI/custom_nodes/basic_data_handling
RUN if [ -f /opt/ComfyUI/custom_nodes/basic_data_handling/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/basic_data_handling/requirements.txt; fi
RUN git clone https://github.com/JayLyu/blender-in-comfyui /opt/ComfyUI/custom_nodes/blender-in-comfyui
RUN git -C /opt/ComfyUI/custom_nodes/blender-in-comfyui checkout 7f626ced25cdd7dc3cfe429450472bea3cd792b3
RUN if [ -f /opt/ComfyUI/custom_nodes/blender-in-comfyui/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/blender-in-comfyui/requirements.txt; fi
RUN git clone https://github.com/alastor-666-1933/caching_to_not_waste /opt/ComfyUI/custom_nodes/caching_to_not_waste
RUN if [ -f /opt/ComfyUI/custom_nodes/caching_to_not_waste/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/caching_to_not_waste/requirements.txt; fi
RUN git clone https://github.com/user-attachments/assets /opt/ComfyUI/custom_nodes/comfyui-art-venture
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui-art-venture/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui-art-venture/requirements.txt; fi
RUN git clone https://github.com/IRCSS/comfyUI-blender-wrapper /opt/ComfyUI/custom_nodes/comfyUI-blender-wrapper
RUN git -C /opt/ComfyUI/custom_nodes/comfyUI-blender-wrapper checkout 17b1ed102dc77df7ccdf08ca50dbecfdf1299131
RUN git clone https://github.com/user-attachments/assets /opt/ComfyUI/custom_nodes/comfyui-detail-daemon
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui-detail-daemon/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui-detail-daemon/requirements.txt; fi
RUN git clone https://github.com/yolain/ComfyUI-Easy-Use /opt/ComfyUI/custom_nodes/ComfyUI-Easy-Use
RUN git -C /opt/ComfyUI/custom_nodes/ComfyUI-Easy-Use checkout 81c510c06e18dffd4f43518644fc35964c9168ca
RUN if [ -f /opt/ComfyUI/custom_nodes/ComfyUI-Easy-Use/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/ComfyUI-Easy-Use/requirements.txt; fi
RUN git clone https://github.com/erosDiffusion/ComfyUI-enricos-nodes.git /opt/ComfyUI/custom_nodes/comfyui-enricos-nodes
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui-enricos-nodes/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui-enricos-nodes/requirements.txt; fi
RUN git clone https://github.com/ggerganov/llama.cpp /opt/ComfyUI/custom_nodes/ComfyUI-GGUF
RUN if [ -f /opt/ComfyUI/custom_nodes/ComfyUI-GGUF/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/ComfyUI-GGUF/requirements.txt; fi
RUN git clone https://github.com/giriss/comfy-image-saver /opt/ComfyUI/custom_nodes/comfyui-image-saver
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui-image-saver/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui-image-saver/requirements.txt; fi
RUN git clone https://github.com/facebookresearch/sam2 /opt/ComfyUI/custom_nodes/comfyui-impact-pack
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui-impact-pack/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui-impact-pack/requirements.txt; fi
RUN git clone https://github.com/lllyasviel/Fooocus /opt/ComfyUI/custom_nodes/comfyui-inpaint-nodes
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui-inpaint-nodes/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui-inpaint-nodes/requirements.txt; fi
RUN git clone https://github.com/comfyanonymous/ComfyUI /opt/ComfyUI/custom_nodes/comfyui-logic
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui-logic/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui-logic/requirements.txt; fi
RUN git clone https://github.com/ltdrdata/ComfyUI-Manager /opt/ComfyUI/custom_nodes/ComfyUI-Manager
RUN git -C /opt/ComfyUI/custom_nodes/ComfyUI-Manager checkout f41365abe95723d078ce2946e82dfb7bc6e9d9c7
RUN if [ -f /opt/ComfyUI/custom_nodes/ComfyUI-Manager/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/ComfyUI-Manager/requirements.txt; fi
RUN git clone https://github.com/Smirnov75/comfyui-mxtoolkit /opt/ComfyUI/custom_nodes/comfyui-mxtoolkit
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui-mxtoolkit/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui-mxtoolkit/requirements.txt; fi
RUN git clone https://github.com/filliptm/ComfyUI_Fill-Nodes /opt/ComfyUI/custom_nodes/comfyui_fill-nodes
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui_fill-nodes/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui_fill-nodes/requirements.txt; fi
RUN git clone https://github.com/chflame163/ComfyUI_LayerStyle_Advance /opt/ComfyUI/custom_nodes/comfyui_layerstyle
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui_layerstyle/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui_layerstyle/requirements.txt; fi
RUN git clone https://github.com/Comfy-Org/cookiecutter-comfy-extension /opt/ComfyUI/custom_nodes/comfyui_sunxAI_facetools
RUN if [ -f /opt/ComfyUI/custom_nodes/comfyui_sunxAI_facetools/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/comfyui_sunxAI_facetools/requirements.txt; fi
RUN git clone https://github.com/brucew4yn3rp/ComfyUI_VintageEffect /opt/ComfyUI/custom_nodes/ComfyUI_VintageEffect
RUN git -C /opt/ComfyUI/custom_nodes/ComfyUI_VintageEffect checkout 9f7c52c992a3ca7b9498799291fae2ccc53360d2
RUN if [ -f /opt/ComfyUI/custom_nodes/ComfyUI_VintageEffect/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/ComfyUI_VintageEffect/requirements.txt; fi
RUN git clone https://github.com/mozhaa/ComfyUI-Execute-Python /opt/ComfyUI/custom_nodes/execute-python
RUN git -C /opt/ComfyUI/custom_nodes/execute-python checkout f6a4a844eb72601dcd9766b10dfd7148415dffbc
RUN if [ -f /opt/ComfyUI/custom_nodes/execute-python/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/execute-python/requirements.txt; fi
RUN git clone https://github.com/ClownsharkBatwing/RES4LYF /opt/ComfyUI/custom_nodes/RES4LYF
RUN git -C /opt/ComfyUI/custom_nodes/RES4LYF checkout 419de2d7c78f415dde9aa352a7231820ebfc17a4
RUN if [ -f /opt/ComfyUI/custom_nodes/RES4LYF/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/RES4LYF/requirements.txt; fi
RUN git clone https://github.com/comfyanonymous/ComfyUI /opt/ComfyUI/custom_nodes/scale-image-to-total-pixels-advanced
RUN if [ -f /opt/ComfyUI/custom_nodes/scale-image-to-total-pixels-advanced/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/scale-image-to-total-pixels-advanced/requirements.txt; fi
RUN git clone https://github.com/Ltamann/ComfyUI-TBG-SAM3 /opt/ComfyUI/custom_nodes/tbg-sam3
RUN git -C /opt/ComfyUI/custom_nodes/tbg-sam3 checkout f6155bfb6deddf55172ade7c104973d52d100527
RUN if [ -f /opt/ComfyUI/custom_nodes/tbg-sam3/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/tbg-sam3/requirements.txt; fi
RUN git clone https://github.com/comfyanonymous/ComfyUI /opt/ComfyUI/custom_nodes/was-ns
RUN if [ -f /opt/ComfyUI/custom_nodes/was-ns/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/was-ns/requirements.txt; fi
RUN pip install timm transformers fairscale pycocoevalcap opencv-python qrcode==[pil] pytorch_lightning kornia pydantic segment_anything omegaconf boto3 matplotlib diffusers accelerate clip_interrogator==0.6.0 lark onnxruntime opencv-python-headless sentencepiece spandrel peft gguf==0.13.0 protobuf piexif segment-anything scikit-image scipy numpy dill GitPython PyGithub matrix-nio huggingface-hub typer rich typing-extensions toml uv chardet librosa sounddevice glitch_this PyOpenGL glfw requests aiohttp moviepy==1.0.3 reportlab openai PyPDF2 pdf2image PyMuPDF ollama gdown open_clip_torch google-genai google-cloud-storage fal-client runwayml httpx huggingface_hub pillow torch scikit_image scikit_learn opencv-contrib-python pymatting colour-science blend_modes loguru ultralytics==8.0.0 mediapipe==0.10.0 pytest==7.4.0 flake8==6.0.0 black==23.0.0 insightface onnxruntime-gpu==; sys_platform != 'darwin' and platform_machine == 'x86_64' cvlib py-machineid pywavelets decord==0.6.0 av==9.0.0 hydra-core==1.3.0 einops==0.6.0 pycocotools==2.0.6 shapely==1.8.0 ftfy==6.1.1 regex iopath==0.1.10 typing_extensions tqdm==4.65.0 cmake imageio joblib numba==0.62 pilgram rembg scikit-learn
COPY runpod_worker /opt/tryon/runpod_worker
WORKDIR /opt/tryon/runpod_worker
RUN pip install -r requirements.txt
COPY runtime-builder/entrypoint.sh /opt/tryon/entrypoint.sh
RUN chmod +x /opt/tryon/entrypoint.sh
ENTRYPOINT ["/opt/tryon/entrypoint.sh"]
