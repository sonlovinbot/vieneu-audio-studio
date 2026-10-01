"""LoRA fine-tuning for VieNeu-TTS v3 Turbo.

Three small modules, all built on the inference classes shipped in the ``vieneu`` SDK:

* :mod:`.data`  — turns (phones, codes, speaker embedding) rows of ONE speaker into the
  2-D token sequences the model reads (no in-context reference), and pads a batch.
* :mod:`.model` — teacher-forcing forward pass + loss for the v3 Turbo network.
* :mod:`.lora`  — attach LoRA adapters (PEFT), save / load / merge them.
"""
from .data import V3TurboLoraDataset, collate_batch, load_rows
from .model import compute_loss, forward_train
from .lora import attach_lora, lora_state_dict, merge_lora_into, save_adapter, load_adapter

__all__ = [
    "V3TurboLoraDataset", "collate_batch", "load_rows",
    "compute_loss", "forward_train",
    "attach_lora", "lora_state_dict", "merge_lora_into", "save_adapter", "load_adapter",
]
