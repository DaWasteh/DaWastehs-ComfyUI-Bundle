#!/usr/bin/env python3
"""Fail-closed, manifest-driven Pixaroma Prompt/Pause integration."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; WF=ROOT/'workflows'; MAN=ROOT/'tools/pixaroma_prompt_manifest.json'; MARK='dawasteh_pixaroma_prompt_integration'
PAUSES={
'workflows/Audio to Image/FLUX2_Klein_4B_BF16+Gemma4_E4B-Audio-to-Image.json':(19,8,6),
'workflows/Audio to Video/FLUX2_Klein_4B_BF16+Gemma4_E4B-Audio-to-AudioReact-Video.json':(16,3,13),
'workflows/Image Editing/FLUX2_Klein_9B_KV_FP8+Qwen3_5_4B-Image-to-Prompt-to-Image.json':(212,6,259),
'workflows/Text to Image/FLUX2_Klein_9B_KV_FP8+Qwen3_5_4B-Idea-to-Prompt-to-Image.json':(212,6,259),
'workflows/Music Generation/StableAudio3_Medium_FP32+Gemma4_E4B-Text-to-Music.json':(30,5,20),
'workflows/Music Generation/StableAudio3_Medium_FP32+Gemma4_E4B-Text-to-Sound.json':(30,5,20),
'workflows/Text to Image/Krea2_Turbo_FP8-Idea-to-Prompt-to-2K-Image.json':(212,6,259),
'workflows/Text to Image/Krea2_Turbo_FP8+Qwen3VL_4B_Abliterated-Idea-to-Prompt-to-Image.json':(214,6,262),
'workflows/Prompt Tools/Pixaroma-Find-and-Replace+ZImage.json':(207,6,247)}
FORMULA_PATHS={'workflows/Music Generation/StableAudio3_Medium_FP32+Gemma4_E4B-Text-to-Music.json','workflows/Music Generation/StableAudio3_Medium_FP32+Gemma4_E4B-Text-to-Sound.json','workflows/Prompt Enhancer/LLM_Qwen3_5_4B_BF16-Text-to-Prompt.json','workflows/Prompt Enhancer/LLM_Qwen3VL_8B_FP8-Idea-to-Krea2-Prompt.json','workflows/Prompt Tools/Pixaroma-Find-and-Replace+ZImage.json','workflows/Text to Image/FLUX2_Klein_9B_KV_FP8+Qwen3_5_4B-Idea-to-Prompt-to-Image.json','workflows/Text to Image/Krea2_Turbo_FP8-Idea-to-Prompt-to-2K-Image.json','workflows/Text to Image/Krea2_Turbo_FP8+Qwen3VL_4B_Abliterated-Idea-to-Prompt-to-Image.json'}
QWEN={'workflows/Image Editing/Qwen_Image_Edit_2511_BF16+Action_LoRA-Image-Edit.json':(231,0),'workflows/Image Fusion/Krea2_Turbo_FP8-Three-Images-to-Image-Fusion.json':(6,0)}
def h(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
sha=h
def read(p):return p.read_text(encoding='utf-8')
def load(p):return json.loads(read(p))
def head_data(p):
 raw=subprocess.check_output(['git','show',f'HEAD:{p.relative_to(ROOT).as_posix()}'],text=True,encoding='utf-8')
 return json.loads(raw)
def write(p,d,raw):
 # Preserve HEAD's one-line vs pretty style exactly.
 one='\n' not in raw.strip()
 text=json.dumps(d,ensure_ascii=False,separators=(',',':')) if one else json.dumps(d,ensure_ascii=False,indent=2)
 p.write_text(text+ ('\n' if raw.endswith('\n') else ''),encoding='utf-8')
def ni(n,name):return next((i for i,x in enumerate(n.get('inputs',[])) if x.get('name')==name),None)
def target_select(path,d):
 out=[]; folder=path.parts[-2]
 if folder in {'LoRA Generation','Image Utilities','Pixaroma Node Demos','Templates & Tests'}:return out
 for n in d['nodes']:
  v=n.get('widgets_values',[]); typ=n.get('type'); title=(n.get('title') or '').lower()
  if not isinstance(v,list):continue
  if typ=='CLIPTextEncode' and v and isinstance(v[0],str) and v[0].strip():
   text_slot=ni(n,'text')
   unlinked=text_slot is None or n['inputs'][text_slot].get('link') is None
   bad='negative' in title or 'negativ' in title or any(x in v[0].lower() for x in ('worst quality','bad anatomy','jpeg artifacts'))
   if unlinked and not bad:out.append((n,'text',0,'direct'))
  if typ=='CLIPTextEncodeFlux' and len(v)>1 and isinstance(v[1],str) and v[1].strip() and ni(n,'t5xxl') is not None and n['inputs'][ni(n,'t5xxl')].get('link') is None and 'negativ' not in title:out.append((n,'t5xxl',1,'direct'))
  if typ=='TextEncodeAceStepAudio1.5' and v and isinstance(v[0],str) and v[0].strip() and ni(n,'tags') is not None and n['inputs'][ni(n,'tags')].get('link') is None:out.append((n,'tags',0,'music'))
  if typ=='HeartMuLaMusicGenerator' and len(v)>1 and isinstance(v[1],str) and v[1].strip() and ni(n,'tags') is not None:out.append((n,'tags',1,'music'))
  if typ=='YUE_Stage_A_Sampler' and v and isinstance(v[0],str) and v[0].strip() and ni(n,'genres_prompt') is not None:out.append((n,'genres_prompt',0,'music'))
  if typ=='MMAudioSuiteSampler' and len(v)>5 and isinstance(v[5],str) and v[5].strip() and ni(n,'prompt') is not None:out.append((n,'prompt',5,'audio'))
  if typ in {'AILab_Qwen3TTSVoiceDesign','FB_Qwen3TTSVoiceDesign'}:
   port='instruct'; idx=ni(n,port)
   if idx is not None and idx<len(v) and isinstance(v[idx],str) and v[idx].strip() and n['inputs'][idx].get('link') is None:out.append((n,port,idx,'voice-direction'))
 for n in d['nodes']:
  if path.relative_to(ROOT).as_posix() in FORMULA_PATHS and n.get('type')=='StringConcatenate' and len(n.get('widgets_values',[]))>1 and n['widgets_values'][1].strip():out.append((n,'string_b',1,'formula'))
 if path.relative_to(ROOT).as_posix() in QWEN:
  nid,idx=QWEN[path.relative_to(ROOT).as_posix()];n=next(x for x in d['nodes'] if x['id']==nid)
  if n['widgets_values'][idx].strip():out.append((n,'prompt',idx,'qwen-edit'))
 return out
def manifest():
 es=[]
 for p in sorted(WF.rglob('*.json')):
  d=head_data(p); ts=target_select(p,d); rel=p.relative_to(ROOT).as_posix(); e={'path':rel,'action':'integrate' if ts or rel in PAUSES else 'skip','reason':'eligible human-editable prompt fields' if ts else ('approved LLM gate' if rel in PAUSES else 'no conservative eligible field'),'targets':[]}
  for n,port,idx,kind in ts:e['targets'].append({'node_id':n['id'],'node_type':n['type'],'input':port,'widget_index':idx,'kind':kind,'source_hash':h(n['widgets_values'][idx]),'source_text':n['widgets_values'][idx]})
  if rel in PAUSES:
   s,t,l=PAUSES[rel];e['pauses']=[{'source_node':s,'source_slot':0,'target_node':t,'target_link':l}]
  es.append(e)
 return {'version':2,'workflow_count':len(es),'entries':es}
def rect(n):
 p=n.get('pos',[0,0]);s=n.get('size',[260,120]);return(p[0],p[1],p[0]+s[0],p[1]+s[1])
def pos(nodes,size,near):
 obs=[rect(n) for n in nodes]; x,y=near
 for r in range(1,100):
  for px,py in ((x-550-r*20,y+r*40),(x+r*40,y+350+r*30),(x-550-r*30,y-350-r*30)):
   q=(px,py,px+size[0],py+size[1])
   if not any(q[0]<b[2] and q[2]>b[0] and q[1]<b[3] and q[3]>b[1] for b in obs):return[px,py]
 raise RuntimeError('no collision-free placement')
def prompt(nid,text,at,target):return {'id':nid,'type':'PixaromaPrompt','title':'Prompt Pixaroma','pos':at,'size':[470,230],'flags':{},'order':0,'mode':0,'inputs':[{'label':'text','name':'text_in','shape':7,'type':'STRING','link':None}],'outputs':[{'name':'text','type':'STRING','links':[]}],'properties':{'cnr_id':'ComfyUI-Pixaroma','ver':'fc17bd2b58ef0089cc62a40502669cf71ae86db7','Node name for S&R':'PixaromaPrompt','promptState':{'text':text,'order':'mine','sep':', ','accent':None,'showExpanded':True},MARK:{'kind':'prompt','target':target}},'widgets_values':[''],'color':'#1e3323','bgcolor':'#36543d'}
def pause_node(nid,at,input_link,output_link):return {'id':nid,'type':'PixaromaPauseText','title':'Approve LLM text','pos':at,'size':[535,492],'flags':{},'order':0,'mode':0,'inputs':[{'name':'text','shape':7,'type':'STRING','link':input_link}],'outputs':[{'name':'text','type':'STRING','links':[output_link]}],'properties':{'cnr_id':'ComfyUI-Pixaroma','ver':'fc17bd2b58ef0089cc62a40502669cf71ae86db7','Node name for S&R':'PixaromaPauseText','pauseTextState':{'gate':'pause','text':'','original':''},MARK:{'kind':'pause','pause_target':output_link}},'widgets_values':['']}
def validate_prompt(d,t):
 ns={n['id']:n for n in d['nodes']}; n=ns[t['node_id']]; slot=ni(n,t['input']);
 if slot is None:return False
 link=n['inputs'][slot].get('link'); ps=[x for x in d['nodes'] if x.get('properties',{}).get(MARK,{}).get('target')==[n['id'],t['input']]]
 if len(ps)!=1: return False
 p=ps[0]; L=next((x for x in d['links'] if x[0]==link),None); expected=prompt(p['id'],t['source_text'],p.get('pos'),[n['id'],t['input']]);expected['outputs'][0]['links']=[link]
 # Workflow refinement may add localized labels and recompute topological order;
 # accept those presentation-only fields while retaining strict schema/state checks.
 expected['order']=p.get('order',0)
 if 'title' not in p:expected.pop('title',None)
 for actual_item, expected_item in zip(p.get('inputs',[]),expected.get('inputs',[])):
  if 'localized_name' in actual_item:expected_item['localized_name']=actual_item['localized_name']
 for actual_item, expected_item in zip(p.get('outputs',[]),expected.get('outputs',[])):
  if 'localized_name' in actual_item:expected_item['localized_name']=actual_item['localized_name']
 return p==expected and n['widgets_values'][t['widget_index']]=='' and L==[link,p['id'],0,n['id'],slot,'STRING']
def apply(p,e,check):
 raw=read(p);d=json.loads(raw);ns={n['id']:n for n in d['nodes']};changed=0
 for t in e['targets']:
  if validate_prompt(d,t):continue
  n=ns.get(t['node_id']);slot=ni(n,t['input']) if n else None
  if n and slot is None and t['kind']=='formula':
   n.setdefault('inputs',[]).append({'name':'string_b','type':'STRING','widget':{'name':'string_b'},'link':None});slot=len(n['inputs'])-1
  if n and slot is None and t['kind']=='direct' and n.get('type')=='CLIPTextEncode':
   n.setdefault('inputs',[]).append({'name':'text','type':'STRING','widget':{'name':'text'},'link':None});slot=len(n['inputs'])-1
  if not n or n.get('type')!=t['node_type'] or slot is None or n['inputs'][slot].get('link') is not None or n['widgets_values'][t['widget_index']]!=t['source_text'] or h(n['widgets_values'][t['widget_index']])!=t['source_hash']:raise RuntimeError(f'{p}: corrupt prompt target')
  nid=max([d.get('last_node_id',0)]+[x['id'] for x in d['nodes']])+1;lid=max([d.get('last_link_id',0)]+[x[0] for x in d['links']])+1; q=prompt(nid,t['source_text'],pos(d['nodes'],[470,230],n.get('pos',[0,0])),[n['id'],t['input']]);q['outputs'][0]['links']=[lid]
  d['nodes'].append(q);d['links'].append([lid,nid,0,n['id'],slot,'STRING']);n['inputs'][slot]['link']=lid;n['widgets_values'][t['widget_index']]='';d['last_node_id']=nid;d['last_link_id']=lid;ns[nid]=q;changed+=1
 for g in e.get('pauses',[]):
  old=next((x for x in d['links'] if x[0]==g['target_link']),None); gates=[x for x in d['nodes'] if x.get('properties',{}).get(MARK,{}).get('pause_target')==g['target_link']]
  if gates:
   gate=gates[0]; fresh=gate.get('inputs',[{}])[0].get('link'); freshlink=next((x for x in d['links'] if x[0]==fresh),None); expected=pause_node(gate['id'],gate.get('pos'),fresh,g['target_link'])
   expected['order']=gate.get('order',0)
   for field in ('color','bgcolor'):
    if field in gate:expected[field]=gate[field]
   for actual_item, expected_item in zip(gate.get('inputs',[]),expected.get('inputs',[])):
    if 'localized_name' in actual_item:expected_item['localized_name']=actual_item['localized_name']
   for actual_item, expected_item in zip(gate.get('outputs',[]),expected.get('outputs',[])):
    if 'localized_name' in actual_item:expected_item['localized_name']=actual_item['localized_name']
   if len(gates)!=1 or gate!=expected or not freshlink or freshlink!=[fresh,g['source_node'],g['source_slot'],gate['id'],0,'STRING'] or old[1]!=gate['id'] or old[2]!=0:raise RuntimeError(f'{p}: corrupt pause gate')
   continue
  if not old or old[1]!=g['source_node'] or old[2]!=g['source_slot'] or old[3]!=g['target_node']:raise RuntimeError(f'{p}: pause source mismatch')
  src=ns[g['source_node']];tar=ns[g['target_node']];nid=max([d.get('last_node_id',0)]+[x['id'] for x in d['nodes']])+1;lid=max([d.get('last_link_id',0)]+[x[0] for x in d['links']])+1
  gate=pause_node(nid,pos(d['nodes'],[535,492],tar.get('pos',[0,0])),lid,old[0])
  src['outputs'][g['source_slot']]['links'].remove(old[0]);src['outputs'][g['source_slot']]['links'].append(lid);d['links'].append([lid,src['id'],g['source_slot'],nid,0,'STRING']);old[1]=nid;old[2]=0;d['nodes'].append(gate);d['last_node_id']=nid;d['last_link_id']=lid;changed+=1
 if changed and not check:write(p,d,raw)
 return changed
def main():
 a=argparse.ArgumentParser();a.add_argument('--write-manifest',action='store_true');a.add_argument('--apply',action='store_true');a.add_argument('--check',action='store_true');a.add_argument('--audit',type=Path);x=a.parse_args()
 if sum((x.write_manifest,x.apply,x.check))!=1:raise SystemExit('choose exactly one of --write-manifest, --apply, or --check')
 if x.write_manifest:write(MAN,manifest(),read(MAN) if MAN.exists() else '{}');return
 m=load(MAN); paths={p.relative_to(ROOT).as_posix():p for p in WF.rglob('*.json')}; manifest_paths={e['path'] for e in m['entries']}
 # The v2 manifest is the immutable migration plan for its historical 186-file
 # baseline. New workflows may be authored with Pixaroma nodes already present;
 # require every manifest entry to remain available without forcing later files
 # into the one-shot migration plan.
 if len(manifest_paths)!=m['workflow_count'] or not manifest_paths<=set(paths):raise SystemExit('manifest coverage mismatch')
 changed=0
 for e in m['entries']:
  if e['action']=='integrate':changed+=apply(paths[e['path']],e,x.check)
 r={'files':len(paths),'integrated_files':sum(e['action']=='integrate' for e in m['entries']),'skip_files':sum(e['action']=='skip' for e in m['entries']),'prompt_files':sum(bool(e.get('targets')) for e in m['entries']),'prompt_targets':sum(len(e['targets']) for e in m['entries']),'pause_files':sum(bool(e.get('pauses')) for e in m['entries']),'pause_gates':sum(len(e.get('pauses',[])) for e in m['entries']),'modified_files':sum(bool(e.get('targets') or e.get('pauses')) for e in m['entries']),'pending':changed if x.check else 0,'changed':changed if x.apply else 0};print(json.dumps(r,indent=2));
 if x.audit:write(x.audit,r,'{}')
 if x.check and changed:raise SystemExit(1)
if __name__=='__main__':main()
