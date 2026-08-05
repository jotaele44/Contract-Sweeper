from __future__ import annotations
import subprocess,sys,unittest
from pathlib import Path
class TestUnifiedSkillpack(unittest.TestCase):
 def test_conformance(self):
  r=Path(__file__).resolve().parents[1]; p=subprocess.run([sys.executable,str(r/"tools/validate_unified_skillpacks.py"),"--root",str(r)],text=True,capture_output=True); self.assertEqual(p.returncode,0,p.stdout+"\n"+p.stderr)
if __name__=="__main__": unittest.main()
