# Makefile Usage Guide 🛠️

This guide explains how to use the `Makefile` in this repository to automate the setup, environment checks, and running the application. The `Makefile` simplifies complex tasks and ensures you have all necessary dependencies.

---

## ⚙️ How to Install `make`

If the `make` command is not found on your system, follow the instructions for your OS:

### Windows

- **Chocolatey** (Recommended): `choco install make`
- **Winget**: `winget install GnuWin32.Make`
- **MSYS2**: `pacman -S make`
- **Git Bash**: `make` is often included with "Git for Windows SDK". Alternatively, download `make.exe` from a trusted source and add it to your PATH.

### macOS

- **Homebrew**: `brew install make`
- **Xcode Tools**: Run `xcode-select --install` in your terminal. This will install a suite of developer tools including `make`.

### Linux

- **Ubuntu/Debian**: `sudo apt update && sudo apt install make`
- **Arch Linux**: `sudo pacman -S make`
- **Fedora**: `sudo dnf install make`

---

## 📋 Quick Reference

| Command           | Description                                                                   |
| ----------------- | ----------------------------------------------------------------------------- |
| `make check`      | Check system toolchain (Python, uv, eSpeak, Docker, GPU, .env, etc.)          |
| `make setup-gpu`  | Full setup for GPU (Interactive dependency check + `uv sync`)                 |
| `make setup-cpu`  | Full setup for CPU (Interactive dependency check + temporary dependency swap) |
| `make demo`       | Run the Gradio UI application                                                 |
| `make docker-gpu` | Start Docker environment with GPU support                                     |
| `make docker-cpu` | Start Docker environment for CPU only                                         |
| `make uv`         | Install or update `uv` package manager                                        |
| `make espeak`     | Install or guide for installing `eSpeak NG`                                   |
| `make clean`      | Clean up build artifacts, `.venv`, and caches                                 |

---

## 🔍 Detailed Command Guide

### 1. `make check`

The environment investigator. Run this first to see what's missing on your system.

- Checks Python version (≥ 3.12 required).
- Detects your GPUs (NVIDIA, Intel, AMD).
- Checks for `uv`, `eSpeak NG`, `Docker`, and `.env` file.
- **Color-coded output**: `[OK]` (Green), `[WARNING]` (Yellow), `[ERROR]` (Red/Fatal).

### 2. `make setup-gpu` / `make setup-cpu`

Automated setup with **interactive dependency checks**.

- Before installing Python packages, it verifies `python`, `uv`, and `eSpeak NG`.
- **Interactive Prompts**: If a tool is missing, it will ask if you want to install it.
  - Windows: Guidance for manual downloads or `winget`.
  - macOS: Uses `brew`.
  - Linux: Uses `apt` or `pacman`.
- **Fail-Fast**: If critical dependencies are missing and not installed, it stops immediately to prevent broken environment states.

### 3. `make uv` / `make espeak`

Standalone installation targets for the core toolchain.

- `make uv`: Runs the official installation script for your OS.
- `make espeak`: Tries automated installation (Winget/Brew/Apt) or provides direct download links.

### 4. `make demo`

Once setup is complete, use this to launch the Gradio web interface. It uses `uv run` to ensure it uses the correct virtual environment.

### 5. `make docker-gpu` / `make docker-cpu`

Simplified Docker commands.

- Automatically handles the creation of a `.env` file from `.env.example` if it's missing.
- Sets the appropriate Docker profile for your detected hardware.

---

## 💻 OS Support

The `Makefile` is designed to be cross-platform and has been tested on:

- **Windows**: (via Git Bash / MSYS2)
- **macOS**: (Intel and Apple Silicon)
- **Linux**: (Ubuntu, Debian, Arch Linux)

---

## 🧹 Cleaning up

If you need to reset your environment or clear disk space:

```bash
make clean
```

This removes `.venv`, `__pycache__`, and other temporary files.
