import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from vieneu.fast import FastVieNeuTTS

@pytest.fixture
def mock_fast_tts():
    with patch("lmdeploy.pipeline") as mock_pipeline, \
         patch("lmdeploy.GenerationConfig"), \
         patch.object(FastVieNeuTTS, '_warmup_model'), \
         patch("vieneu.standard.BaseVieneuTTS._load_codec") as mock_codec:
        
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.return_value = [MagicMock(text="codes"), MagicMock(text="codes")]
        mock_pipeline.return_value = mock_pipeline_instance
        
        with patch.object(FastVieNeuTTS, '_load_codec'):
            tts = FastVieNeuTTS(backbone_device="cuda")
            tts.codec = MagicMock()
            tts.codec.device = "cuda"
            tts.codec.decode_code.return_value = np.zeros((1, 1, 1000))
            return tts

def test_fast_init(mock_fast_tts):
    assert mock_fast_tts.backbone is not None
    assert mock_fast_tts.device == "cuda"

def test_fast_infer(mock_fast_tts):
    with patch("vieneu_utils.phonemize_text.phonemize_with_dict", return_value="phonemes"), \
         patch.object(mock_fast_tts, '_decode', return_value=np.zeros(1000)):
        audio = mock_fast_tts.infer("Xin chào", ref_codes=[1, 2], ref_text="ref")
        assert isinstance(audio, np.ndarray)
        assert len(audio) == 1000

def test_fast_infer_batch(mock_fast_tts):
    texts = ["Text 1", "Text 2"]
    with patch("vieneu.fast.phonemize_batch", return_value=["p1", "p2"]) as mock_ph_batch, \
         patch.object(mock_fast_tts, '_decode', return_value=np.zeros(1000)):
        results = mock_fast_tts.infer_batch(texts, ref_codes=[1], ref_text="ref")
        assert len(results) == 2
        mock_ph_batch.assert_called_once()
