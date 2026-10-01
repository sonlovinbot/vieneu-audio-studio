

def Vieneu(mode="v3turbo", **kwargs):
    """
    Factory function for VieNeu-TTS.

    Args:
        mode: 'v3turbo' (DEFAULT) — VieNeu-TTS v3 Turbo, 48 kHz. CPU runs torch-free
              via ONNX Runtime; GPU uses PyTorch. Works with the minimal install.
              'v3nano' — VieNeu-TTS v3 Nano, 24 kHz, ONNX/CPU only, torch-free. A
              48M-parameter flow model for WEAK CPUs where v3 Turbo is too slow.
              Preset voices + voice cloning; English / code-switched text is
              noticeably weaker than v3 Turbo. Pick it only when Turbo can't keep up.
              Other modes need extras (``pip install vieneu[gpu]``):
              'standard' (CPU/GPU-GGUF), 'fast' (GPU-LMDeploy), 'turbo'/'turbo_gpu',
              'remote' (API), 'xpu' (Intel GPU).
        **kwargs: Arguments for chosen class

    Returns:
        BaseVieneuTTS: An instance of a VieNeu-TTS implementation.
    """
    match mode:
        case "v3turbo":
            from .v3turbo import V3TurboVieNeuTTS
            return V3TurboVieNeuTTS(**kwargs)
        case "v3nano":
            from .v3nano import V3NanoVieNeuTTS
            return V3NanoVieNeuTTS(**kwargs)
        case "remote" | "api":
            from .remote import RemoteVieNeuTTS
            return RemoteVieNeuTTS(**kwargs)
        case "fast" | "gpu":
            from .fast import FastVieNeuTTS
            return FastVieNeuTTS(**kwargs)
        case "turbo":
            from .turbo import TurboVieNeuTTS
            return TurboVieNeuTTS(**kwargs)
        case "turbo_gpu":
            from .turbo import TurboGPUVieNeuTTS
            return TurboGPUVieNeuTTS(**kwargs)
        case "xpu":
            try:
                from .core_xpu import XPUVieNeuTTS
                return XPUVieNeuTTS(**kwargs)
            except Exception as e:
                raise RuntimeError(f"Failed to load XPU backend. Ensure Intel GPU drivers and torch.xpu are installed: {e}") from e
        case "standard":
            from .standard import VieNeuTTS
            return VieNeuTTS(**kwargs)
