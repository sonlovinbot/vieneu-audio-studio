SHELL := /bin/bash

.PHONY: help setup setup-gpu setup-cpu setup-finetune demo run stream docker-cpu docker-gpu docker-build-cpu docker-build-gpu check clean

help:
	@echo "Targets:"
	@echo "  make check          - check toolchain (python>=3.10, uv, docker, gpu, .env...)"
	@echo "  make setup          - torch-free install: v3 Turbo (ONNX) + v3 Nano on CPU"
	@echo "  make setup-gpu      - + torch/transformers: v3 Turbo on CUDA (uv sync --extra cuda)"
	@echo "  make setup-finetune - + peft/accelerate: LoRA fine-tuning (uv sync --extra finetune)"
	@echo "  make run            - run Gradio UI (alias for 'make demo')"
	@echo "  make stream         - run legacy Web Stream UI (v1 CPU GGUF)"
	@echo "  make docker-cpu     - docker compose --profile cpu (Web UI, torch-free)"
	@echo "  make docker-gpu     - docker compose --profile gpu (Web UI, CUDA)"
	@echo "  make clean          - clean artifacts (.venv, cache, ...)"
	@echo "  make uv          - install uv (standalone)"
	@echo "  make espeak      - install eSpeak NG (standalone)"

# --- Setup ---
check-install-prereqs:
	@set -euo pipefail; \
	C_GREEN='\033[0;32m'; \
	C_YELLOW='\033[1;33m'; \
	C_RED='\033[0;31m'; \
	C_RESET='\033[0m'; \
	echo ">> Checking prerequisites..."; \
	OS_TYPE="unknown"; \
	if [[ "$$OSTYPE" == "msys" || "$$OSTYPE" == "cygwin" || "$$OSTYPE" == "win32" ]]; then OS_TYPE="windows"; fi; \
	if [[ "$$OSTYPE" == "darwin"* ]]; then OS_TYPE="macos"; fi; \
	if [[ "$$OSTYPE" == "linux-gnu"* ]]; then OS_TYPE="linux"; fi; \
	\
	# --- Python Check --- \
	if ! command -v python >/dev/null 2>&1; then \
	  echo -e "$${C_YELLOW}[WARNING] Python not found.$${C_RESET}"; \
	  read -p "Install Python 3.12? [y/N] " ans; \
	  if [[ "$$ans" =~ ^[Yy]$$ ]]; then \
	    if [ "$$OS_TYPE" == "windows" ]; then \
	       echo "Installing Python via winget..."; \
	       winget install -e --id Python.Python.3.12 || { echo -e "$${C_RED}[ERROR] Install failed.$${C_RESET}"; exit 1; }; \
	    elif [ "$$OS_TYPE" == "macos" ]; then \
	       echo "Installing via brew..."; \
	       brew install python@3.12 || { echo -e "$${C_RED}[ERROR] Install failed.$${C_RESET}"; exit 1; }; \
	    elif [ "$$OS_TYPE" == "linux" ]; then \
	       echo "Installing via apt/pacman (guessing)..."; \
	       (sudo apt update && sudo apt install -y python3-full) || (sudo pacman -S --noconfirm python) || { echo -e "$${C_RED}[ERROR] Install failed.$${C_RESET}"; exit 1; }; \
	    else \
	       echo -e "$${C_RED}[ERROR] OS not detected. Please install Python 3.12 manually.$${C_RESET}"; exit 1; \
	    fi; \
	  else \
	    echo -e "$${C_RED}[ERROR] Python is required. Aborting.$${C_RESET}"; exit 1; \
	  fi; \
	fi; \
	# --- uv Check --- \
	if ! command -v uv >/dev/null 2>&1; then \
	  echo -e "$${C_YELLOW}[WARNING] uv not found.$${C_RESET}"; \
	  read -p "Install uv? [y/N] " ans; \
	  if [[ "$$ans" =~ ^[Yy]$$ ]]; then \
	    if [ "$$OS_TYPE" == "windows" ]; then \
	       echo "Installing uv via Powershell..."; \
	       powershell -c "irm https://astral.sh/uv/install.ps1 | iex" || { echo -e "$${C_RED}[ERROR] Install failed.$${C_RESET}"; exit 1; }; \
	    else \
	       echo "Installing uv via curl..."; \
	       curl -LsSf https://astral.sh/uv/install.sh | sh || { echo -e "$${C_RED}[ERROR] Install failed.$${C_RESET}"; exit 1; }; \
	    fi; \
	  else \
	    echo -e "$${C_RED}[ERROR] uv is required. Aborting.$${C_RESET}"; exit 1; \
	  fi; \
	fi; \
	# --- eSpeak (legacy v1/v2 backends only; v3 uses sea-g2p) --- \
	if ! command -v espeak-ng >/dev/null 2>&1 && ! command -v espeak >/dev/null 2>&1; then \
	   echo -e "$${C_BLUE}[INFO] eSpeak NG not found — only needed for the legacy v1/v2 backends (make espeak).$${C_RESET}"; \
	fi

uv:
	@echo ">> Installing uv..."
	@if [ "$$(uname -o 2>/dev/null)" = "Msys" ] || [ "$$(uname -o 2>/dev/null)" = "Cygwin" ]; then \
	    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"; \
	else \
	    curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi

espeak:
	@echo ">> Installing eSpeak NG..."
	@if [ "$$(uname -o 2>/dev/null)" = "Msys" ] || [ "$$(uname -o 2>/dev/null)" = "Cygwin" ]; then \
	   # Try winget first
	   if command -v winget >/dev/null 2>&1; then \
	       echo "Trying winget..."; \
	       winget install -e --id eSpeak-NG.eSpeak-NG || { echo "Winget failed/not found. Opening download page..."; start https://github.com/espeak-ng/espeak-ng/releases; }; \
	   else \
	       echo "Opening download page..."; \
	       start https://github.com/espeak-ng/espeak-ng/releases; \
	   fi; \
	elif [ "$$(uname)" = "Darwin" ]; then \
	    brew install espeak; \
	elif command -v apt >/dev/null 2>&1; then \
	    sudo apt update && sudo apt install -y espeak-ng; \
	elif command -v pacman >/dev/null 2>&1; then \
	    sudo pacman -S --noconfirm espeak-ng; \
	else \
	    echo "Unknown OS/Manager. Please install espeak-ng manually."; \
	fi

setup: check-install-prereqs
	uv sync

setup-cpu: setup

setup-gpu: check-install-prereqs
	uv sync --extra cuda

setup-finetune: check-install-prereqs
	uv sync --extra finetune

demo:
	uv run vieneu-web

run: demo

stream:
	uv run vieneu-stream

# --- Docker (auto-create .env if missing) ---
docker-cpu:
	@set -euo pipefail; \
	if [ ! -f .env ] && [ -f .env.example ]; then cp .env.example .env; echo ">> Created .env from .env.example"; fi; \
	docker compose -f docker/docker-compose.yml --profile cpu up

docker-gpu:
	@set -euo pipefail; \
	if [ ! -f .env ] && [ -f .env.example ]; then cp .env.example .env; echo ">> Created .env from .env.example"; fi; \
	docker compose -f docker/docker-compose.yml --profile gpu up

docker-build-cpu:
	docker build -t pnnbao/vieneu-tts:cpu -f docker/Dockerfile.cpu .

docker-build-gpu:
	docker build -t pnnbao/vieneu-tts:gpu -f docker/Dockerfile.gpu .

# --- Docker Serve (LEGACY v1/v2 LMDeploy API server) ---
docker-build-serve:
	docker build -t pnnbao/vieneu-tts:serve -f docker/Dockerfile.serve .

docker-push-serve:
	docker push pnnbao/vieneu-tts:serve

# --- Environment/version checks ---
check:
	@set -euo pipefail; \
	C_CYAN='\033[0;36m'; \
	C_GREEN='\033[0;32m'; \
	C_YELLOW='\033[1;33m'; \
	C_RED='\033[0;31m'; \
	C_BLUE='\033[0;34m'; \
	C_RESET='\033[0m'; \
	echo -e "$${C_CYAN}== System ==$${C_RESET}"; \
	uname -a || true; \
	echo; \
	echo -e "$${C_CYAN}== Python ==$${C_RESET}"; \
	if command -v python >/dev/null 2>&1; then \
	  python -V; \
	  python -c 'import sys; ok = sys.version_info >= (3,10); print("python_ok(>=3.10):", ok); sys.exit(0 if ok else 2)' && echo -e "$${C_GREEN}[OK]$${C_RESET} Python version OK" || echo -e "$${C_YELLOW}[WARNING]$${C_RESET} Python should be >= 3.10 (repo requirement)."; \
	else \
	  echo -e "$${C_RED}[ERROR]$${C_RESET} python not found. Need Python >= 3.10."; \
	fi; \
	echo; \
	echo -e "$${C_CYAN}== uv ==$${C_RESET}"; \
	if command -v uv >/dev/null 2>&1; then \
	  uv --version; \
	  echo -e "$${C_GREEN}[OK]$${C_RESET} uv found"; \
	else \
	  echo -e "$${C_YELLOW}[WARNING]$${C_RESET} uv not found (repo uses uv sync/uv run)."; \
	fi; \
	echo; \
	echo -e "$${C_CYAN}== eSpeak NG (legacy v1/v2 only) ==$${C_RESET}"; \
	if command -v espeak-ng >/dev/null 2>&1; then \
	  espeak-ng --version | head -n 1; \
	  echo -e "$${C_GREEN}[OK]$${C_RESET} eSpeak NG found"; \
	elif command -v espeak >/dev/null 2>&1; then \
	  espeak --version | head -n 1; \
	  echo -e "$${C_GREEN}[OK]$${C_RESET} eSpeak found"; \
	else \
	  echo -e "$${C_BLUE}[INFO]$${C_RESET} eSpeak NG not found (only the legacy v1/v2 backends need it)."; \
	fi; \
	echo; \
	echo -e "$${C_CYAN}== Docker ==$${C_RESET}"; \
	if command -v docker >/dev/null 2>&1; then \
	  docker --version; \
	  echo -e "$${C_GREEN}[OK]$${C_RESET} Docker found"; \
	else \
	  echo -e "$${C_BLUE}[INFO]$${C_RESET} docker not found (only needed for docker-* targets)."; \
	fi; \
	if docker compose version >/dev/null 2>&1; then \
	  docker compose version; \
	  echo -e "$${C_GREEN}[OK]$${C_RESET} Docker Compose found"; \
	else \
	  echo -e "$${C_BLUE}[INFO]$${C_RESET} docker compose plugin not found."; \
	fi; \
	if [ -f .env ]; then \
	  echo -e "$${C_GREEN}[OK]$${C_RESET} .env file found"; \
	else \
	  echo -e "$${C_YELLOW}[WARNING]$${C_RESET} .env file not found (will be created from .env.example when running docker-* targets)."; \
	fi; \
	echo; \
	echo -e "$${C_CYAN}== GPU ==$${C_RESET}"; \
	echo "Detected your GPUs (System):"; \
	IS_WINDOWS=false; \
	if [[ "$$OSTYPE" == "msys" || "$$OSTYPE" == "cygwin" || "$$OSTYPE" == "win32" ]]; then IS_WINDOWS=true; fi; \
	if [ "$$IS_WINDOWS" = true ]; then \
	    powershell "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name" || echo "Could not list GPUs"; \
	elif [[ "$$OSTYPE" == "darwin"* ]]; then \
	    system_profiler SPDisplaysDataType | grep "Chipset Model" | sed 's/.*Chipset Model: //' || echo "Could not list GPUs"; \
	elif command -v lspci >/dev/null 2>&1; then \
	    lspci | grep -i 'vga\|3d\|display' || echo "No GPUs found via lspci"; \
	else \
	    echo "Universal GPU detection not supported on this OS/Toolchain."; \
	fi; \
	echo; \
	if command -v nvidia-smi >/dev/null 2>&1; then \
	  echo -e "$${C_GREEN}[OK]$${C_RESET} NVIDIA GPU detected"; \
	  nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1; \
	  echo "CUDA Version (Driver):"; \
	  nvidia-smi --query-gpu=cuda_version --format=csv,noheader | head -n 1 || echo "N/A"; \
	  echo "CUDA Toolkit (nvcc):"; \
	  nvcc --version | grep release | sed 's/.*release //' | sed 's/,.*//' || echo -e "$${C_YELLOW}[WARNING] Not found$${C_RESET}"; \
	  echo "GPU(s):"; \
	  nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader | while read line; do echo "  GPU $$line"; done || nvidia-smi -L; \
	else \
	  echo -e "$${C_BLUE}[INFO]$${C_RESET} nvidia-smi not found (OK for CPU-only mode)."; \
	fi; \
	echo; \
	echo -e "$${C_CYAN}== Repo files ==$${C_RESET}"; \
	ls -1 pyproject.toml uv.lock 2>/dev/null && echo -e "$${C_GREEN}[OK]$${C_RESET} All required files found" || echo -e "$${C_YELLOW}[WARNING]$${C_RESET} Some files missing"

clean:
	rm -rf .venv __pycache__ .pytest_cache
