"""Materialize candidate, committee, recipient resolution, and graph edges."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from scripts.campaign_finance_common import stable_id
from scripts.config import PROJECT_ROOT, setup_logging
try:
    from scripts.analyze_political_crossref import _normalize as norm
except Exception:
    def norm(v):
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(v or "").upper())).strip()

CAND_COLS=["candidate_entity_id","fec_candidate_id","canonical_name","normalized_name","party","office_sought","cycles","source_datasets","confidence","review_status"]
COMM_COLS=["committee_entity_id","fec_committee_id","canonical_name","normalized_name","committee_type","party","state","source_datasets","confidence","review_status"]
RECIP_COLS=["recipient_resolution_id","recipient_name","normalized_name","resolved_entity_id","resolved_entity_name","resolved_entity_type","match_method","confidence","review_status","total_disbursements","disbursement_count","committees_paying","cycles"]
EDGE_COLS=["edge_id","source_entity_id","source_entity_type","edge_type","target_entity_id","target_entitytype","amount","transaction_date","cycle","support_oppose_indicator","source_dataset","confidence"]

def read(p): return pd.read_csv(p,dtype=str,low_memory=False).fillna("") if p.exists() else pd.DataFrame()
def pipe(values): return "|".join(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))
def is_committee(row):
    text=" ".join(str(row.get(c,"")) for c in ("candidate_or_committee","candidacy_type","office_sought","report_type")).lower()
    return any(x in text for x in ("comite","comité","committee","partido","pac"))

def build_candidates(p):
    rows=[]
    for fn,source in (("pr_fec_contributions.csv","fec_a"),("pr_fec_independent_expenditures.csv","fec_e")):
        df=read(p/fn)
        for _,r in df.iterrows():
            name=r.get("candidate_name",""); cid=r.get("candidate_id","")
            if name or cid: rows.append((cid,name or cid,""," ".join(x for x in (r.get("office",""),r.get("office_state",""),r.get("office_district","")) if x),r.get("cycle",""),source))
    for fn,source in (("pr_donaciones.csv","cee"),("pr_oce_donations.csv","oce")):
        for _,r in read(p/fn).iterrows():
            if not is_committee(r) and r.get("candidate_or_committee",""):
                rows.append(("",r["candidate_or_committee"],r.get("party",""),r.get("office_sought","") or r.get("candidacy_type",""),r.get("cycle",""),source))
    if not rows: return pd.DataFrame(columns=CAND_COLS)
    df=pd.DataFrame(rows,columns=["fec","name","party","office","cycle","source"]); df["n"]=df.name.map(norm); df=df[df.n!=""]
    out=[]
    for n,g in df.groupby("n"):
        fec=next((x for x in g.fec if x),""); sources=sorted(set(g.source)); conf=95 if fec else 82 if len(sources)>1 else 68
        out.append([fec or stable_id("candidate",n),fec,g.name.iloc[0],n,pipe(g.party),pipe(g.office),pipe(sorted(set(g.cycle))),"|".join(sources),conf,"confirmed" if conf>=90 else "probable" if conf>=70 else "needs_review"])
    return pd.DataFrame(out,columns=CAND_COLS).sort_values("canonical_name")

def build_committees(p):
    rows=[]
    for _,r in read(p/"pr_fec_committees.csv").iterrows(): rows.append((r.get("committee_id",""),r.get("name","") or r.get("committee_id",""),r.get("committee_type_full","") or r.get("committee_type",""),r.get("party_full","") or r.get("party",""),r.get("state",""),"fec_master"))
    for _,r in read(p/"pr_fec_contributions.csv").iterrows():
        if r.get("committee_name","") or r.get("committee_id",""): rows.append((r.get("committee_id",""),r.get("committee_name","") or r.get("comittee_id",""),"","","","fec_a"))
    for _,r in read(p/"pr_oce_reports.csv").iterrows():
        rows.append(("",row.get("committee_name",""),row.get("report_type",""),"","PR","oce_reports"))
    for fn,source in (("pr_donaciones.csv","cee"),("pr_oce_donations.csv","oce")):
        for _,r in read(p/fn).iterrows():
            if is_committee(r): rows.append(("",row.get("candidate_or_committee",""),row.get("candidacy_type",""),r.get("party",""),"PR",source))
    df=pd.DataFrame(rows,columns=["fec","name","type","party","state","source"]); df["n"]=df.name.map(norm); df=df[df.n!=""]
    out=[]
    for n,g in df.groupby("n"):
        fec=next((x for x in g.fec if x),""); sources=sorted(set(g.source)); conf=96 if fec else 84 if len(sources)>1 else 70
        out.append([fec or stable_id("committee",n),fec,g.name.iloc[0],n,pipe(g.type),pipe(g.party),pipe(g.state),"|".join(sources),conf,"confirmed" if conf>=90 else "probable"])
    return pd.DataFrame(out,columns=COMM_COLS).sort_values("canonical_name")

def resolve_recipients(p,cands,comms):
    df=read(p/"pr_fec_disbursements.csv")
    if df.empty or "recipient_name" not in df: return pd.DataFrame(columns=RECIP_COLS)
    idx={r.normalized_name:(r.candidate_entity_id,r.canonical_name,"candidate",96) for r in cands.itertuples()}; idx.update({r.normalized_name:(r.committee_entity_id,r.canonical_name,"committee",96) for r in comms.itertuples()})
    for fn,namecol,idcol,kind in (("ngos/ngos_master.csv","legal_name","ngo_id","ngo"),("entities_resolved.csv","canonical_name","entity_id","entity"),("pr_all_awards_master.csv","recipient_name","recipient_uei","award_recipient")):
        for _,r in read(p/fn).iterrows():
            n=norm(r.get(namecol,""));
            if n and n not in idx: idx[n]=(r.get(idcol,"") or stable_id(kind,n),r.get(namecol,""),kind,84)
    df["n"]=df.recipient_name.map(norm); df["amt"]=pd.to_numeric(df.get("disbursement_amount",""),errors="coerce").fillna(0); out=[]
    for n,g in df[df.n!=""].groupby("n"):
        hit=idx.get(n); eid,ename,kind,conf=hit if hit else ("","","unresolved",0)
        out.append([stable_id("recipient",n),g.recipient_name.iloc[0],n,eid,ename,kind,"exact_normalized_name" if hit else "unresolved",conf,"confirmed" if conf>=90 else "probable" if conf else "needs_review",float(g.amt.sum()),len(g),pipe(g.get("committee_name",pd.Series(dtype=str))),pipe(g.get("cycle",pd.Series(dtype=str)))])
    return pd.DataFrame(out,columns=RECIP_COLS).sort_values("total_disbursements",ascending=False)

def build_edges(p,cands,comms):
    cbid={r.fec_candidate_id:r.candidate_entity_id for r in cands.itertuples() if r.fec_candidate_id}; cbn={r.normalized_name:r.candidate_entity_id for r in cands.itertuples()}; mbid={r.fec_committee_id:r.committee_entity_id for r in comms.itertuples() if r.fec_committee_id}; edges=[]
    for i,r in read(p/"pr_fec_contributions.csv").iterrows():
        target=mbid.get(r.get("committee_id","")); donor=norm(r.get("contributor_name",""))
        if target and donor: edges.append([stable_id("cfedge","fec_a",i,donor,target),stable_id("donor",donor),"individual" if str(r.get("is_individual","")).lower()=="true" else "organization","CONTRIBUTED_TO",target,"committee",r.get("contribution_receipt_amount",""),r.get("contribution_receipt_date",""),r.get("cycle",""),"","fec_schedule_a",95])
    for i,r in read(p/"pr_fec_independent_expenditures.csv").iterrows():
        source=mbid.get(r.get("committee_id","")); target=cbid.get(r.get("candidate_id","")) or cbn.get(norm(r.get("candidate_name","")))
        if source and target:
            ind=r.get("support_oppose_indicator",""); et="SUPPORTED" if ind.upper().startswith("S") else "OPPOSED" if ind.upper().startswith("O") else "INDEPENDENT_EXPENDITURE_FOR"
            edges.append([stable_id("cfedge","fec_e",i,source,target),source,"committee",et,target,"candidate",r.get("expenditure_amount",""),r.get("expenditure_date",""),r.get("cycle",""),ind,"fec_schedule_e",98])
    return pd.DataFrame(edges,columns=EDGE_COLS)

def run(root=None):
    root=Path(root) if root else PROJECT_ROOT; p=root/"data/staging/processed"; p.mkdir(parents=True,exist_ok=True); log=setup_logging("build_campaign_finance_entities")
    cands=build_candidates(p); comms=build_committees(p); recips=resolve_recipients(p,cands,comms); edges=build_edges(p,cands,comms)
    outputs={"candidates":cands,"committees":comms,"recipient_resolution":recips,"edges":edges}
    for key,df in outputs.items(): df.to_csv(p/f"pr_campaign_finance_{key}.csv",index=False)
    result={"status":"OK","candidates":len(cands),"committees":len(comms),"recipients":len(recips),"resolved_recipients":int((recips.resolved_entity_type!="unresolved").sum()) if len(recips) else 0,"edges":len(edges)}; log.info(json.dumps(result)); return result
if __name__=="__main__": print(json.dumps(run(),indent=2))
