import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "tools/start_live_avatar_workflow12.ps1"
STOP = ROOT / "tools/stop_live_avatar_workflow12.ps1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


FAKE_SERVICE = r'''
import argparse, json, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--token-file',required=True);p.add_argument('--identity',required=True);p.add_argument('--face',required=True);p.add_argument('--model-set',required=True);p.add_argument('--asset-set',required=True);a=p.parse_args();a.token=__import__('pathlib').Path(a.token_file).read_text(encoding='ascii').strip()
health={'candidate':'DeepFaceLive','provider':'DmlExecutionProvider','vendor_id':'0x1002','adapter_name':'AMD Radeon AI PRO R9700','adapter_luid':'0x00000001:0x00000002','model_set_sha256':a.model_set,'identity_id':a.identity,'asset_set_sha256':a.asset_set,'run_token_required':True,'origin_validation':True,'reports_process_id':True,'process_id':os.getpid(),'ready':True}
class H(BaseHTTPRequestHandler):
 def log_message(self,*x):pass
 def authorized(self):
  origin=self.headers.get('Origin');
  if origin and origin!='http://127.0.0.1':self.send_response(403);self.end_headers();return False
  if self.headers.get('Authorization')!='Bearer '+a.token:self.send_response(401);self.end_headers();return False
  return True
 def reply(self,obj):
  data=json.dumps(obj).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_GET(self):
  if not self.authorized():return
  self.reply(health)
 def do_POST(self):
  # Drain the tiny fixture body before closing on 401/403; otherwise Windows
  # can reset the connection and hide the status from Invoke-WebRequest.
  self.rfile.read(int(self.headers.get('Content-Length', '0')))
  if not self.authorized():return
  self.reply({'accepted':True})
  if self.path.endswith('/shutdown'):threading.Thread(target=self.server.shutdown,daemon=True).start()
s=ThreadingHTTPServer(('127.0.0.1',a.port),H);s.serve_forever()
'''


@unittest.skipUnless(sys.platform == "win32", "Windows PowerShell supervisor test")
class SupervisorIntegrationTests(unittest.TestCase):
    def test_verified_start_warmup_and_external_kill_switch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            service = root / "fake_service.py"
            service.write_text(FAKE_SERVICE, encoding="utf-8")
            face = root / "face.png"
            face.write_bytes(b"authorized integration face")
            python = Path(sys.executable).resolve()
            model_hash = sha256(service)
            model_set = hashlib.sha256(model_hash.encode("ascii")).hexdigest()
            face_hash = sha256(face)
            asset_set = hashlib.sha256(face_hash.encode("ascii")).hexdigest()
            port = 18972
            config = {
                "mode": "quality",
                "visible_disclosure": "AI AVATAR TEST",
                "allowed_roots": [str(root), str(python.parent)],
                "consent": {
                    "identity_id": "integration-identity",
                    "attestation_id": "integration-attestation",
                    "subject": "fully synthetic integration fixture",
                    "status": "active",
                    "expires_at": "2100-01-01T00:00:00Z",
                    "allowed_destinations": ["local-integration-test"],
                    "adult": False,
                    "fully_synthetic": True,
                    "minor": False,
                    "public_figure": False,
                    "face_authorized": True,
                    "voice_authorized": False,
                    "revoked": False,
                    "deleted": False,
                    "assets": [{"purpose": "face", "path": str(face), "sha256": face_hash}],
                },
                "quality": {
                    "name": "DeepFaceLive",
                    "enabled": True,
                    "executable": str(python),
                    "executable_sha256": sha256(python),
                    "working_directory": str(root),
                    "arguments": [
                        "{MODEL_0}", "--port", str(port), "--token-file", "{RUN_TOKEN_FILE}",
                        "--identity", "{IDENTITY_ID}", "--face", "{FACE_ASSET}",
                        "--model-set", model_set, "--asset-set", asset_set,
                    ],
                    "health_url": f"http://127.0.0.1:{port}/health",
                    "warmup_url": f"http://127.0.0.1:{port}/warmup",
                    "shutdown_url": f"http://127.0.0.1:{port}/shutdown",
                    "expected_health": {
                        "candidate": "DeepFaceLive",
                        "provider": "DmlExecutionProvider",
                        "vendor_id": "0x1002",
                        "adapter_name": "AMD Radeon AI PRO R9700",
                        "adapter_luid": "0x00000001:0x00000002",
                        "model_set_sha256": model_set,
                        "identity_id": "integration-identity",
                        "asset_set_sha256": asset_set,
                        "run_token_required": True,
                        "origin_validation": True,
                        "reports_process_id": True,
                        "ready": True,
                    },
                    "directml_attestation": {
                        "provider": "DmlExecutionProvider",
                        "vendor_id": "0x1002",
                        "adapter_name": "AMD Radeon AI PRO R9700",
                        "adapter_luid": "0x00000001:0x00000002",
                    },
                    "models": [{"path": str(service), "sha256": model_hash}],
                },
                "candidate": {"enabled": False},
                "rvc": {"enabled": False},
                "obs": {"enabled": False},
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            run_root = root / "runs"
            supervisor = subprocess.Popen(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START),
                    "-ConfigPath", str(config_path), "-RunRoot", str(run_root), "-ReadyTimeoutSeconds", "20",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            try:
                pointer = run_root / "current-manifest.txt"
                deadline = time.time() + 30
                manifest_path = None
                while time.time() < deadline:
                    if pointer.is_file():
                        manifest_path = Path(pointer.read_text(encoding="utf-8-sig").strip())
                        if manifest_path.is_file():
                            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                            if manifest.get("status") == "ready":
                                break
                    if supervisor.poll() is not None:
                        break
                    time.sleep(0.2)
                output_so_far = ""
                if supervisor.poll() is not None and supervisor.stdout:
                    output_so_far = supervisor.stdout.read()
                self.assertIsNotNone(manifest_path, output_so_far)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                self.assertEqual(manifest.get("status"), "ready", output_so_far)
                self.assertFalse(manifest.get("publicStreamLaunchRequested"))
                self.assertNotIn("runToken", manifest)
                stopped = subprocess.run(
                    [
                        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(STOP),
                        "-ManifestPath", str(manifest_path), "-RunRoot", str(run_root),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=40,
                )
                self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
                supervisor.wait(timeout=15)
                final = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                self.assertEqual(final["status"], "stopped")
                self.assertFalse((manifest_path.parent / "run-token.txt").exists())
            finally:
                if supervisor.poll() is None:
                    supervisor.kill()
                    supervisor.wait(timeout=5)
                if supervisor.stdout is not None:
                    supervisor.stdout.close()


if __name__ == "__main__":
    unittest.main()
