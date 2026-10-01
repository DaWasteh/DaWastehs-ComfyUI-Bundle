#!/usr/bin/env python3
"""Generate the five curated local image-LoRA training workflows."""
from __future__ import annotations
import json
from pathlib import Path

OUT = Path("workflows/LoRA Generation")
CONFIGS = [
 ("ZImage_Base_BF16-Images-to-LoRA.json", "zimage-base", "Z-Image Base", "Z-Image\\z_image_bf16.safetensors", ("CLIPLoader", ["Qwen\\qwen_3_4b.safetensors", "lumina2", "default"]), "FLUX\\ae.safetensors", False),
 ("Boogu_Image_Base_BF16-Images-to-LoRA.json", "boogu-image-base", "Boogu Image Base", "Boogu\\boogu_image_base_bf16.safetensors", ("CLIPLoader", ["Qwen\\qwen3vl_8b_fp8_scaled.safetensors", "boogu", "default"]), "FLUX\\flux1_vae_bf16.safetensors", False),
 ("FLUX1_Dev_FP8-Images-to-LoRA.json", "flux1-dev", "FLUX.1 Dev (experimentell)", "FLUX\\flux1-dev-fp8.safetensors", ("DualCLIPLoader", ["clip_l.safetensors", "T5\\t5xxl_fp8_e4m3fn.safetensors", "flux", "default"]), "FLUX\\ae.safetensors", True),
 ("FLUX2_Klein_Base_4B_BF16-Images-to-LoRA.json", "flux2-klein-4b-base", "FLUX.2 Klein 4B Base", "FLUX\\flux-2-klein-base-4b.safetensors", ("CLIPLoader", ["Qwen\\qwen_3_4b.safetensors", "flux2", "default"]), "FLUX2\\flux2-vae.safetensors", False),
]

def socket(name, typ, link=None, widget=False):
 d={"name":name,"type":typ,"link":link}
 if widget:d["widget"]={"name":name}
 return d

def node(i,t,x,y,inputs,outputs,widgets=None,title=None,size=(300,180)):
 d={"id":i,"type":t,"pos":[x,y],"size":list(size),"flags":{},"order":i-1,"mode":0,"inputs":inputs,"outputs":outputs,"properties":{"Node name for S&R":t}}
 if widgets is not None:d["widgets_values"]=widgets
 if title:d["title"]=title
 return d

def build(filename,slug,label,unet,clip,vae,flux=False,sdxl=False):
 nodes=[]; links=[]; nid=1; lid=1
 def add(t,x,y,ins,outs,w=None,title=None,size=(300,180)):
  nonlocal nid
  n=node(nid,t,x,y,ins,outs,w,title,size);nodes.append(n);nid+=1;return n
 def link(a,ao,b,bi,typ):
  nonlocal lid
  links.append([lid,a["id"],ao,b["id"],bi,typ]);a["outputs"][ao].setdefault("links",[]).append(lid);b["inputs"][bi]["link"]=lid;lid+=1
 dataset=add("LoadImageTextDataSetFromFolder",0,0,[socket("folder","COMBO",widget=True)],[{"name":"images","type":"IMAGE","links":[]},{"name":"texts","type":"STRING","links":[]}],[f"lora_training/{slug}"],"Dataset aus ComfyUI input")
 preview=add("PreviewImage",500,0,[socket("images","IMAGE")],[{"name":"images","type":"IMAGE","links":[]}],None,"Dataset-Vorschau")
 link(dataset,0,preview,0,"IMAGE")
 if sdxl:
  loader=add("CheckpointLoaderSimple",0,500,[socket("ckpt_name","COMBO",widget=True)],[{"name":"MODEL","type":"MODEL","links":[]},{"name":"CLIP","type":"CLIP","links":[]},{"name":"VAE","type":"VAE","links":[]}],["SDXL\\RealVisXL_V4.0.safetensors"])
  model=clipn=vaen=loader; mo=0;co=1;vo=2
 else:
  model=add("UNETLoader",0,500,[socket("unet_name","COMBO",widget=True),socket("weight_dtype","COMBO",widget=True)],[{"name":"MODEL","type":"MODEL","links":[]}],[unet,"default"]);mo=0
  ct,cw=clip
  cin=[socket("clip_name","COMBO",widget=True),socket("type","COMBO",widget=True),socket("device","COMBO",widget=True)] if ct=="CLIPLoader" else [socket("clip_name1","COMBO",widget=True),socket("clip_name2","COMBO",widget=True),socket("type","COMBO",widget=True),socket("device","COMBO",widget=True)]
  clipn=add(ct,0,1000,cin,[{"name":"CLIP","type":"CLIP","links":[]}],cw);co=0
  vaen=add("VAELoader",0,1500,[socket("vae_name","COMBO",widget=True)],[{"name":"VAE","type":"VAE","links":[]}],[vae]);vo=0
 if flux:
  sampling=add("ModelSamplingFlux",500,500,[socket("model","MODEL"),socket("max_shift","FLOAT",widget=True),socket("base_shift","FLOAT",widget=True),socket("width","INT",widget=True),socket("height","INT",widget=True)],[{"name":"MODEL","type":"MODEL","links":[]}],[1.15,.5,1024,1024]);link(model,mo,sampling,0,"MODEL");model=sampling;mo=0
 make=add("MakeTrainingDataset",1000,800,[socket("images","IMAGE"),socket("vae","VAE"),socket("clip","CLIP"),socket("texts","STRING")],[{"name":"latents","type":"LATENT","links":[]},{"name":"conditioning","type":"CONDITIONING","links":[]}],None,size=(340,220))
 link(dataset,0,make,0,"IMAGE");link(vaen,vo,make,1,"VAE");link(clipn,co,make,2,"CLIP");link(dataset,1,make,3,"STRING")
 bucket=add("ResolutionBucket",1600,800,[socket("latents","LATENT"),socket("conditioning","CONDITIONING")],[{"name":"latents","type":"LATENT","links":[]},{"name":"conditioning","type":"CONDITIONING","links":[]}]);link(make,0,bucket,0,"LATENT");link(make,1,bucket,1,"CONDITIONING")
 train_inputs=[socket("model","MODEL"),socket("latents","LATENT"),socket("positive","CONDITIONING")]+[socket(n,t,widget=True) for n,t in [("batch_size","INT"),("grad_accumulation_steps","INT"),("steps","INT"),("learning_rate","FLOAT"),("rank","INT"),("optimizer","COMBO"),("loss_function","COMBO"),("seed","INT"),("training_dtype","COMBO"),("lora_dtype","COMBO"),("quantized_backward","BOOLEAN"),("algorithm","COMBO"),("gradient_checkpointing","BOOLEAN"),("checkpoint_depth","INT"),("offloading","BOOLEAN"),("existing_lora","COMBO"),("bucket_mode","BOOLEAN"),("bypass_mode","BOOLEAN")]]
 offload = slug == "boogu-image-base"
 vals=[1,4,2,.0001,16,"AdamW","MSE",42,"none" if flux else "bf16","bf16",flux,"LoRA",True,1,offload,"[None]",True,flux]
 train=add("TrainLoraNode",2200,650,train_inputs,[{"name":"lora","type":"LORA_MODEL","links":[]},{"name":"loss_map","type":"LOSS_MAP","links":[]},{"name":"steps","type":"INT","links":[]}],vals,"Lokales LoRA-Training",(390,620));link(model,mo,train,0,"MODEL");link(bucket,0,train,1,"LATENT");link(bucket,1,train,2,"CONDITIONING")
 loss=add("LossGraphNode",2900,650,[socket("loss","LOSS_MAP"),socket("filename_prefix","STRING",widget=True)],[],[f"lora_training/{slug}_loss"],"LossGraph anzeigen");link(train,1,loss,0,"LOSS_MAP")
 save=add("SaveLoRA",2900,1050,[socket("lora","LORA_MODEL"),socket("prefix","STRING",widget=True),socket("steps","INT")],[],[f"loras/DaWasteh/{slug}_rank16_smoke"],"LoRA lokal speichern");link(train,0,save,0,"LORA_MODEL");link(train,2,save,2,"INT")
 add("PixaromaRunTimer",2900,1450,[],[],[{"version":1,"color":"#f66744","decimals":0,"chime":True,"sound":"","volume":70}],size=(300,100))
 warning="\n\n**EXPERIMENTELL:** Der quantisierte Rückwärtsweg (`training_dtype=none`, `quantized_backward=true`, `bypass_mode=true`) wird erst nach einem lokalen RDNA4-Smoke-Test freigegeben." if flux else ""
 usage=f"# {label} · Lokales Bild-LoRA-Training\n\nDataset unter `ComfyUI/input/lora_training/{slug}` anlegen. Zu jedem Bild gehört eine gleichnamige `.txt`-Datei mit präziser Caption (z. B. `bild01.png` + `bild01.txt`). **2 Schritte sind als sicherer Smoke-Test voreingestellt.** Erst wenn Loss und Dateiausgabe funktionieren, `steps` auf etwa 1000 setzen und `_smoke` aus dem Dateiprefix entfernen.\n\nRDNA4: BF16 und PyTorch-SDPA verwenden; keine CUDA-exklusiven Attention- oder Kernel-Optionen ergänzen. Bei Boogu ist `offloading=true` gegen OOM bereits aktiviert; nicht abschalten, außer ein gemessener Lauf hat ausreichend VRAM-Reserve. `SaveLoRA` schreibt nach `ComfyUI/output/loras/DaWasteh/`; zur Nutzung die fertige Datei anschließend nach `ComfyUI/models/loras/DaWasteh/` kopieren. Der LossGraph liegt ebenfalls unter `output`.{warning}"
 rank="# Rank-Matrix 16 / 32 / 64 / 128\n\n| Rank | Kapazität | Dateigröße | Overfitting |\n|---:|---|---|---|\n| 16 | kompakt, guter Start | klein | geringstes Risiko |\n| 32 | mehr Details | mittel | bei kleinen Sets beobachten |\n| 64 | hohe Stilkapazität | groß | deutlich erhöht |\n| 128 | maximale Kapazität | sehr groß | nur für große, vielfältige Sets |\n\nDie Learning Rate **nicht automatisch erhöhen**, wenn der Rank steigt; zunächst `0.0001` beibehalten. Rank und Dateiprefix gemeinsam ändern."
 add("MarkdownNote",0,2050,[],[],[usage],"Bedienung und Dataset",(700,420));add("MarkdownNote",900,2050,[],[],[rank],"Rank 16/32/64/128",(700,420))
 return {"id":f"local-{slug}-lora-training","revision":0,"last_node_id":nid-1,"last_link_id":lid-1,"nodes":nodes,"links":links,"groups":[],"config":{},"extra":{"ds":{"scale":0.7,"offset":[100,100]}},"version":0.4}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 configs=CONFIGS+[("SDXL_RealVisXL_V4_FP16-Images-to-LoRA.json","sdxl","SDXL",None,None,None,False)]
 for c in configs:
  fn,slug,label,unet,clip,vae,flux=c
  data=build(fn,slug,label,unet,clip,vae,flux,fn.startswith("SDXL"))
  (OUT/fn).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(f"generated {len(configs)} workflows")
if __name__=="__main__":main()
