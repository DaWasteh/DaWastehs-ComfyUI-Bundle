import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=(ROOT/'assets/live-avatar-v072/workflow-10.template.json',ROOT/'workflows/Live Avatar/LiveAvatar-10-Realistic-Adult-Character-Reference-Prompt+Image.json')
class ReferenceWorkflow(unittest.TestCase):
 def test_template_is_release_graph_and_timer_free(self):
  self.assertEqual(FILES[0].read_bytes(),FILES[1].read_bytes())
  graph=json.loads(FILES[0].read_text(encoding='utf8'));self.assertFalse(any(n['type']=='PixaromaRunTimer' for n in graph['nodes']))
 def test_three_clothed_presets_and_safe_prompt_only_nude(self):
  graph=json.loads(FILES[0].read_text(encoding='utf8'));nodes={n['id']:n for n in graph['nodes']};text=' '.join(str(n.get('widgets_values',[])) for n in graph['nodes']).lower()
  for token in ('preset 1','preset 2','preset 3','clearly adult','non-explicit','ambiguous age','malformed hands','fused fingers','user interface','watermark'):self.assertIn(token,text)
  nude=next(n for n in graph['nodes'] if n.get('title','').startswith('Prompt-only adult non-explicit nude'))
  links={link[0]:link for link in graph['links']};model_link=links[nude['inputs'][0]['link']]
  self.assertEqual(nodes[model_link[1]]['type'],'SelectModelDevice')
  selector=nodes[model_link[1]];selector_input=links[selector['inputs'][0]['link']]
  self.assertEqual(nodes[selector_input[1]]['type'],'CheckpointLoaderSimple')
  self.assertNotIn('portrait',nodes[15]['widgets_values'][0].lower())
  self.assertEqual(nodes[19]['mode'],2);self.assertIn('opt-in',nodes[19]['title'].lower())
  start=json.loads(nodes[1]['widgets_values'][0])['content'].lower()
  for seed in ('27031991','27031992','27031993','27032033'):self.assertIn(seed,start)
  self.assertIn('pose is prompt-guided and not guaranteed',start)
 def test_only_pinned_installed_8188_assets_are_selected(self):
  fixture=json.loads((ROOT/'assets/live-avatar-v072/object-info.json').read_text(encoding='utf8'));graph=json.loads(FILES[0].read_text(encoding='utf8'))
  checks={'CheckpointLoaderSimple':('ckpt_name',0),'IPAdapterModelLoader':('ipadapter_file',0),'CLIPVisionLoader':('clip_name',0)}
  for node in graph['nodes']:
   if node['type'] in checks:
    field,index=checks[node['type']];self.assertIn(node['widgets_values'][index],fixture[node['type']]['input']['required'][field][0])
 def test_truthfully_describes_2d_reference_not_automatic_vrm(self):
  text=FILES[0].read_text(encoding='utf8').lower();self.assertIn('reference-image generation only',text);self.assertIn('does not create, rig, skin, auto-rig, or export a vrm',text)
if __name__=='__main__':unittest.main()
