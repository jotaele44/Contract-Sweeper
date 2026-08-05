#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path
def H(b): return hashlib.sha256(b).hexdigest()
def L(p): return json.loads(p.read_text(encoding="utf-8"))
def G(root,*args): return subprocess.run(["git","-C",str(root),*args],text=True,capture_output=True)
def main():
 a=argparse.ArgumentParser(); a.add_argument("--root",default="."); root=Path(a.parse_args().root).resolve(); m=root/".claude/skillpacks"; errors=[]; checks=[]
 b=L(m/"BINDING.json"); x=L(m/"MANIFEST.json"); legacy=L(m/"LEGACY_COMPATIBILITY.json"); skill=(m/"SKILL.md").read_bytes(); text=skill.decode()
 if x["repository"]!=b["repository"] or x["pinned_base_commit"]!=b["pinned_base_commit"]: errors.append("identity/base mismatch")
 if x.get("runtime_enabled") is not False: errors.append("runtime enabled")
 if any(v is not False for v in b["activation"].values()): errors.append("activation not fail-closed")
 if any(v is not False for v in b["authority"].values()): errors.append("authority not fail-closed")
 if H(skill)!=x["skill_sha256"] or len(skill)!=x["skill_bytes"]: errors.append("skill hash/size mismatch")
 ids={c["id"] for c in x["capabilities"]}
 if len(ids)!=x["capability_count"]: errors.append("capability count mismatch")
 for c in x["capabilities"]:
  if f'`{c["id"]}`' not in text: errors.append(f'missing capability {c["id"]}')
  if c.get("replacement") and c["replacement"] not in ids: errors.append(f'alias target missing {c["id"]}')
 if "__unknown_capability__" in ids: errors.append("unknown dispatch sentinel present")
 entries=legacy.get("entries",[]); repo_ids=set(b["capability_ids"])
 if {e["capability_id"] for e in entries}!=repo_ids: errors.append("legacy parity mismatch")
 if any(e.get("status")!="compatibility_shim" or e.get("capability_preserved") is not True for e in entries): errors.append("legacy shim invalid")
 if H((m/"LEGACY_COMPATIBILITY.json").read_bytes())!=x["legacy_compatibility_sha256"]: errors.append("legacy hash mismatch")
 for p in b["implementation_roots"]+b["test_roots"]:
  if not (root/p).exists(): errors.append(f"bound path missing: {p}")
 checks=["identity","non_activation","skill_hash","capability_accounting","alias_resolution","fail_closed_dispatch","legacy_parity","repository_path_bindings"]
 if (root/".git").exists():
  base=b["pinned_base_commit"]
  if G(root,"merge-base","--is-ancestor",base,"HEAD").returncode: errors.append("pinned base not ancestor")
  run=G(root,"diff","--name-only",f"{base}..HEAD")
  if run.returncode: errors.append("git diff failed")
  else:
   changed=[p for p in run.stdout.splitlines() if p]; allowed=x["allowed_change_paths"]
   for p in changed:
    if not any(p==q or (q.endswith("/") and p.startswith(q)) for q in allowed): errors.append(f"out-of-scope change: {p}")
   for q in b["legacy_surfaces"]:
    if any(p==q or p.startswith(q.rstrip("/")+"/") for p in changed): errors.append(f"legacy modified: {q}")
  checks += ["exact_base_ancestry","change_scope","legacy_non_modification"]
 result={"schema_version":"1.0","repository":b["repository"],"pinned_base_commit":b["pinned_base_commit"],"status":"success" if not errors else "failed","checks":checks,"errors":errors,"capability_count":x["capability_count"],"module_count":x["module_count"]}; print(json.dumps(result,indent=2,sort_keys=True)); return 0 if not errors else 1
if __name__=="__main__": raise SystemExit(main())
