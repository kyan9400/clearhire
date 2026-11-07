# syntax=docker/dockerfile:1.7
# Ollama on an NVIDIA GPU through Vulkan.
#
# Ollama's CUDA build needs driver 550+. Hosts with an older driver (this one has 535, and upgrading
# it means rebooting a shared server) can still use the GPU through Vulkan. On a headless server the
# NVIDIA Vulkan driver must be loaded through EGL rather than GLX, and it needs two X11 libraries the
# Ollama image does not have. Build from the repository root:
#   docker build -f deploy/llm/Dockerfile -t clearhire-llm .

FROM ollama/ollama:0.40.10
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxext6 libx11-6 \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/llm/nvidia_icd.json /etc/vulkan/icd.d/nvidia_icd.json
ENV OLLAMA_VULKAN=1 \
    CUDA_VISIBLE_DEVICES=-1 \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics
