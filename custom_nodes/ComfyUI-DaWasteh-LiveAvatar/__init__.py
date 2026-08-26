"""Continuous LivePortrait, cached AI Mirror, and local VRM nodes for ComfyUI."""
from .nodes import DaWastehCachedOpenPose, DaWastehContinuousLiveAvatar, DaWastehLatestLiveAvatarOutput, DaWastehPersistentSpout, DaWastehVRMLiveAvatarLauncher, DaWastehWorkflow12Preflight
from .voice_swap import DaWastehLiveVoiceSwapLauncher
from .vrm_tools import DaWastehRiggedGLBToVRM0, DaWastehVRMTextureSource, DaWastehVRMTextureVariant
from .vrm_server import register_routes

register_routes()
NODE_CLASS_MAPPINGS = {
    "DaWastehCachedOpenPose": DaWastehCachedOpenPose,
    "DaWastehContinuousLiveAvatar": DaWastehContinuousLiveAvatar,
    "DaWastehLatestLiveAvatarOutput": DaWastehLatestLiveAvatarOutput,
    "DaWastehLiveVoiceSwapLauncher": DaWastehLiveVoiceSwapLauncher,
    "DaWastehPersistentSpout": DaWastehPersistentSpout,
    "DaWastehVRMLiveAvatarLauncher": DaWastehVRMLiveAvatarLauncher,
    "DaWastehWorkflow12Preflight": DaWastehWorkflow12Preflight,
    "DaWastehVRMTextureSource": DaWastehVRMTextureSource,
    "DaWastehVRMTextureVariant": DaWastehVRMTextureVariant,
    "DaWastehRiggedGLBToVRM0": DaWastehRiggedGLBToVRM0,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "DaWastehCachedOpenPose": "Cached OpenPose (DaWasteh, webcam optimized)",
    "DaWastehContinuousLiveAvatar": "LivePortrait Continuous Spout (DaWasteh, experimental)",
    "DaWastehLatestLiveAvatarOutput": "Latest Workflow 13 Multiview Output (DaWasteh)",
    "DaWastehLiveVoiceSwapLauncher": "DirectML RVC Live Voice Swap Launcher (DaWasteh)",
    "DaWastehPersistentSpout": "Persistent Latest-Frame Spout (DaWasteh)",
    "DaWastehVRMLiveAvatarLauncher": "VRM Full-Body Live Avatar Launcher (DaWasteh)",
    "DaWastehWorkflow12Preflight": "Workflow 12 Fail-Closed Consent/Launch Preflight (DaWasteh)",
    "DaWastehVRMTextureSource": "VRM Texture Source (DaWasteh, local)",
    "DaWastehVRMTextureVariant": "Save VRM Texture Variant (DaWasteh, local)",
    "DaWastehRiggedGLBToVRM0": "Rigged GLB to VRM0 Candidate (DaWasteh, strict)",
}
WEB_DIRECTORY = "web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
