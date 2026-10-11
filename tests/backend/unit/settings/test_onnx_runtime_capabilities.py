from unittest.mock import patch

from backend.video_summary.infrastructure.runtime_capabilities import detect_runtime_capabilities


def test_nvidia_hardware_does_not_imply_onnx_cuda_support():
    with patch("backend.video_summary.infrastructure.runtime_capabilities._is_nvidia_cuda_available", return_value=True), \
        patch("backend.video_summary.infrastructure.runtime_capabilities.platform.system", return_value="Windows"), \
        patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
        capabilities = detect_runtime_capabilities()
    assert capabilities.nvidia_cuda_available
    assert not capabilities.gpu_embedding_available
    assert capabilities.unavailable_reason
