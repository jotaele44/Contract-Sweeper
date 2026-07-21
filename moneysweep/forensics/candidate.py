from __future__ import annotations
import json, shutil
from pathlib import Path

def generate_candidate(root: Path, version: str) -> Path:
    policy=(root/'config'/'forensics'/'manual_promotion_policy.yaml').read_text(encoding='utf-8')
    if 'allow_automatic_promotion: false' not in policy:
        raise RuntimeError('Manual promotion policy is not enforced')
    queue=json.loads((root/'reports'/'forensics'/'skill_improvement_queue.json').read_text(encoding='utf-8'))
    approved=[p for p in queue if p.get('status') in {'TRIAGED','APPROVED'}]
    target=root/'reports'/'forensics'/'candidates'/version; target.mkdir(parents=True,exist_ok=False)
    shutil.copy2(root/'moneysweep'/'forensics'/'skill'/'SKILL.md',target/'SKILL.md')
    (target/'proposal_manifest.json').write_text(json.dumps(approved,indent=2),encoding='utf-8')
    return target
