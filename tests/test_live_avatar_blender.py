import hashlib,json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class BlenderToolchain(unittest.TestCase):
 def test_pins_and_builder_contract(self):
  m=json.loads((ROOT/'assets/live-avatar-blender/toolchain-manifest.json').read_text());self.assertEqual(m['blender']['sha256'],'41da973b9bf95bb312cbeff4d1982feb13259b43c821686b9bafea4dfe5477cf');self.assertEqual(m['vrm_addon']['sha256'],'e5e0f923a0bb11eb1320870b2db8091948dd5b63014510d839016a112e40a35a')
  b=(ROOT/'tools/build_local_blender_vrm_avatar.py').read_text();self.assertIn("base_sha256",b);self.assertIn("TongueOut",b);self.assertIn('subprocess.run',b);self.assertNotIn('shell=True',b)
 def test_frontend_manual_tongue_contract(self):
  h=(ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/frontend/index.html').read_text();j=(ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/frontend/src/main.js').read_text();self.assertIn('tongueIntensity',h);self.assertIn('Webcam-Zungenerkennung (experimentell)',h);self.assertNotIn('nicht verfügbar',h);self.assertIn('"TongueOut"',j);self.assertIn('key.toLowerCase() === "t"',j);self.assertIn('tongueColorScore',j)
 def test_source_face_decal_preserves_vrm_animation_contract(self):
  source=(ROOT/'tools/blender/add_face_decal_vrm.py').read_text();self.assertIn('Img00031FaceDecal',source);self.assertIn('texture.outputs["Alpha"]',source);self.assertIn('shape_key_add',source);self.assertIn('humanoid Head bone is missing',source);self.assertIn('blend_shape_groups',source)
if __name__=='__main__':unittest.main()
