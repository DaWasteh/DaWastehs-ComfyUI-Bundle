"""Central, linkable device choices for ComfyUI's official Multi-GPU selectors."""
from __future__ import annotations

from inspect import cleandoc
from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

import comfy.model_management

from .adaptive_nodes import DaWAdaptiveLoadImage, DaWAdaptiveLoadVideo


DEFAULT_MODEL_DEVICE = "gpu:0"
DEFAULT_HELPER_DEVICE = "gpu:1"


def _device_options(*, include_cpu: bool) -> list[str]:
    """Return runtime devices while preserving this bundle's portable defaults."""
    options = list(comfy.model_management.get_gpu_device_options())
    if not include_cpu:
        options = [option for option in options if option != "cpu"]
    required = ["default", DEFAULT_MODEL_DEVICE, DEFAULT_HELPER_DEVICE]
    if include_cpu:
        required.insert(1, "cpu")
    for option in required:
        if option not in options:
            options.append(option)
    return options


class DaWMultiGPUDeviceControl(io.ComfyNode):
    """Provide one central set of dropdowns for MODEL, CLIP, and every VAE selector.

    Connect these COMBO outputs to the ``device`` input of ComfyUI's official
    Select Model Device, Select CLIP Device, and Select VAE Device nodes. The
    node chooses labels only; the official selectors remain responsible for
    validating and moving the actual model objects.
    """

    @classmethod
    def define_schema(cls):
        model_options = _device_options(include_cpu=True)
        vae_options = _device_options(include_cpu=False)
        return io.Schema(
            node_id="DaWMultiGPUDeviceControl",
            display_name="DaW Multi-GPU Device Control",
            category="DaWasteh/multigpu",
            description=cleandoc(cls.__doc__),
            inputs=[
                io.Combo.Input("model_device", options=model_options, default=DEFAULT_MODEL_DEVICE),
                io.Combo.Input("clip_device", options=model_options, default=DEFAULT_HELPER_DEVICE),
                io.Combo.Input("vae_device", options=vae_options, default=DEFAULT_HELPER_DEVICE),
            ],
            outputs=[
                io.Combo.Output("model_device"),
                io.Combo.Output("clip_device"),
                io.Combo.Output("vae_device"),
            ],
        )

    @classmethod
    def validate_inputs(cls, **_kwargs):
        # Preserve workflows made on a machine with more GPUs. Official Select
        # * Device nodes provide the runtime fallback for unavailable gpu:N.
        return True

    @classmethod
    def execute(
        cls,
        model_device: str = DEFAULT_MODEL_DEVICE,
        clip_device: str = DEFAULT_HELPER_DEVICE,
        vae_device: str = DEFAULT_HELPER_DEVICE,
    ) -> io.NodeOutput:
        return io.NodeOutput(str(model_device), str(clip_device), str(vae_device))


class DaWMultiGPUControlExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [DaWMultiGPUDeviceControl, DaWAdaptiveLoadImage, DaWAdaptiveLoadVideo]


async def comfy_entrypoint() -> DaWMultiGPUControlExtension:
    return DaWMultiGPUControlExtension()
