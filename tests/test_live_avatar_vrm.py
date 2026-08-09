import hashlib,importlib.util,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/vrm_server.py';S=importlib.util.spec_from_file_location('vrm_server',P);v=importlib.util.module_from_spec(S);S.loader.exec_module(v)
class Request: 
 def __init__(self,remote):self.remote=remote
class VRMTests(unittest.TestCase):
 def test_global_path_loopback_and_traversal(self):
  self.assertEqual(v.model_root(Path('X:/Comfy')),Path('X:/Comfy/models/live-avatar-vrm'))
  self.assertTrue(v.loopback(Request('127.0.0.1')));self.assertFalse(v.loopback(Request('10.0.0.7')))
  with self.assertRaises(ValueError):v.safe_child(v.WEB_ROOT,'../../secret')
 def test_launcher_contract_and_local_built_assets(self):
  n=(ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/nodes.py').read_text();self.assertIn('OUTPUT_NODE = True',n);self.assertIn('"ui": {"text": [url]}',n)
  launcher=(ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/web/vrm_launcher.js').read_text();self.assertIn('follow_framing',launcher);self.assertIn('presentation',launcher);self.assertIn('URLSearchParams',launcher)
  web=ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/web/vrm-app';notices=(web/'THIRD_PARTY_NOTICES.txt').read_text();self.assertTrue(all(x in notices for x in ['MediaPipe','Three.js','three-vrm','Kalidokit','Apache License']));self.assertFalse('http://' in (ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/frontend/src/main.js').read_text())
 def test_generator_is_clean_room_and_byte_stable(self):
  import tempfile
  names=['LiveAvatar-06-VRM-Full-Body-Hand-Face+Live-Mic.json','LiveAvatar-07-AI-Webcam-Character-Swap-Experimental.json','LiveAvatar-08-Local-VRM-Texture-Creator-Realistic+Stylized.json','LiveAvatar-09-Meshy-AutoRig-to-VRM-Candidate-Optional-Cloud.json','LiveAvatar-10-Realistic-Adult-Character-Reference-Prompt+Image.json','LiveAvatar-11-AI-Webcam-Character-Swap-Cached-OpenPose.json']
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);subprocess.run([sys.executable,str(ROOT/'tools/generate_live_avatar_v072_workflows.py'),'--destination',str(out)],check=True,stdout=subprocess.DEVNULL);first=[(out/n).read_bytes() for n in names]
   for n in names:(out/n).write_bytes(b'arbitrary')
   subprocess.run([sys.executable,str(ROOT/'tools/generate_live_avatar_v072_workflows.py'),'--destination',str(out)],check=True,stdout=subprocess.DEVNULL)
   self.assertEqual(first,[(out/n).read_bytes() for n in names]);self.assertEqual(first,[(ROOT/'workflows/Live Avatar'/n).read_bytes() for n in names])
 def test_controls_and_mapping_helpers_are_present(self):
  front=ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/frontend';s=(front/'src/main.js').read_text();html=(front/'index.html').read_text();built=(ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/web/vrm-app/index.html').read_text()
  self.assertIn('loopController',s);self.assertIn('lastFace',s);self.assertIn('enumerateDevices',s);self.assertIn('neutralLegs',s);self.assertIn('handInputs',s);self.assertIn('URL.revokeObjectURL',s);self.assertIn('Tracking-Frame verworfen',s);self.assertIn('targets.captureRest',s);self.assertIn('validPalmLandmarks',s);self.assertIn('Math.min(rawDt, 0.05)',s);self.assertIn('visibleFramePairs',s);self.assertIn('requestVideoFrameCallback', (front/'src/tracking/helpers.js').read_text());self.assertNotIn('removeUnnecessaryJoints',s)
  self.assertIn('globalThis.Holistic',s);self.assertNotIn("from '@mediapipe/holistic'",s);self.assertIn('DirectionalLight',s);self.assertNotIn('HemisphereLight',s);self.assertIn('URLSearchParams(location.search)',s);self.assertIn('params.get("model")',s);self.assertIn('params.get("present")',s);self.assertIn('params.get("chroma")',s);self.assertIn('params.get("follow")',s)
  self.assertIn('./mediapipe/holistic.js',html);self.assertIn('./mediapipe/holistic.js',built)
 def test_vrm_command_uses_live_global_root(self):
  text=(ROOT/'custom_nodes/ComfyUI-DaWasteh-LiveAvatar/README.md').read_text();self.assertIn('--comfy-root L:/ComfyUI/ComfyUI',text)
 def test_high_realism_workflow_and_tools_are_release_managed(self):
  import json
  name='LiveAvatar-15-Local-High-Realism-VRM.json';workflow=json.loads((ROOT/'workflows/Live Avatar'/name).read_text());template=(ROOT/'assets/live-avatar-v080'/name.replace('.json','.template.json')).read_bytes()
  self.assertEqual((ROOT/'workflows/Live Avatar'/name).read_bytes(),template)
  nodes={n['id']:n for n in workflow['nodes']};self.assertEqual(nodes[6]['type'],'Hunyuan3Dv2Conditioning');self.assertEqual(nodes[4]['widgets_values'][0],4096);self.assertEqual(nodes[8]['widgets_values'][1],512);self.assertIn('singleview',nodes[10]['widgets_values'][0])
  self.assertEqual(nodes[2]['type'],'LoadImage');self.assertEqual([i['name'] for i in nodes[2]['inputs']],['image','upload']);self.assertEqual(len(nodes[2]['outputs']),2)
  self.assertEqual(nodes[45]['type'],'RMBG');self.assertEqual(nodes[45]['widgets_values'][0],'RMBG-2.0');self.assertEqual(nodes[45]['widgets_values'][2],1024);self.assertEqual(nodes[45]['widgets_values'][7],'Alpha')
  self.assertIn([15,2,0,45,0,'IMAGE'],workflow['links']);self.assertIn([16,45,0,5,1,'IMAGE'],workflow['links'])
  self.assertNotIn('Hunyuan3Dv2ConditioningMultiView',[n['type'] for n in workflow['nodes']])
  self.assertIn('Workflow 15',nodes[11]['title'])
  for tool in ['rig_hunyuan_high_realism_vrm.py','bake_multiview_pbr_texture.py','add_pbr_roughness.py','downscale_pbr_images.py','add_vrm_face_shapes.py','inspect_glb.py','generate_pbr_roughness.py']:
   self.assertTrue((ROOT/'tools/blender'/tool).is_file(),tool)
  orchestrator=(ROOT/'tools/build_high_realism_local_vrm.py').read_text();self.assertIn('a.output_vrm.parent.mkdir(parents=True,exist_ok=True)',orchestrator)
  rig=(ROOT/'tools/blender/rig_hunyuan_high_realism_vrm.py').read_text();face=(ROOT/'tools/blender/add_vrm_face_shapes.py').read_text();down=(ROOT/'tools/blender/downscale_pbr_images.py').read_text()
  self.assertIn('for donor_mesh in donor_meshes',rig);self.assertNotIn('license_name = "CC0"',rig+face);self.assertIn('factor=2048.0/max(width,height)',down);self.assertNotIn('image.scale(2048,2048)',down)
 def test_v080_generator_includes_high_realism_workflow(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);subprocess.run([sys.executable,str(ROOT/'tools/generate_live_avatar_v080_workflows.py'),'--destination',str(out)],check=True,stdout=subprocess.DEVNULL)
   name='LiveAvatar-15-Local-High-Realism-VRM.json';self.assertEqual((out/name).read_bytes(),(ROOT/'workflows/Live Avatar'/name).read_bytes())
if __name__=='__main__':unittest.main()
