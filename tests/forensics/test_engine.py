from datetime import timedelta
from pathlib import Path
import json
import yaml
from moneysweep.forensics.core import ForensicsLedger, entity_id, pr_contract_action_key, query_key, utcnow


def ledger(tmp_path):
    x=ForensicsLedger(tmp_path/'f.duckdb',Path(__file__).parents[2]/'migrations'/'forensics');x.migrate();return x

def test_repeat_migration(tmp_path):
    x=ledger(tmp_path);x.migrate();assert x.conn.execute('select count(*) from schema_migrations').fetchone()[0]==1;x.close()
def test_contract_collision():
    contractor=entity_id('PR','ACME');assert pr_contract_action_key('ACT','2020-000185',None,contractor)!=pr_contract_action_key('UPR','2020-000185',None,contractor)
def test_upsert_idempotency(tmp_path):
    x=ledger(tmp_path);now=utcnow();r={'source_id':'s','family':'x','endpoint':None,'source_tier':'T1','created_at':now,'updated_at':now};assert x.upsert('sources',[r],['source_id'])['inserted']==1;assert x.upsert('sources',[r],['source_id'])['inserted']==0;x.close()
def test_query_preflight(tmp_path):
    x=ledger(tmp_path);params={'q':'jacobs'};assert x.preflight_query(source_id='ocpr',subject_id='e',query_type='name',parameters=params).action=='RUN';now=utcnow();qk=query_key('ocpr','e','name',params);r={'query_id':'q1','query_key':qk,'source_id':'ocpr','entity_id':'e','project_id':None,'query_type':'name','parameters_json':json.dumps(params),'parameters_hash':'h','started_at':now,'finished_at':now,'status':'SUCCESS_NULL','result_count':0,'new_record_count':0,'updated_record_count':0,'null_result':True,'failure_type':None,'fallback_route':None,'retry_after':None,'fresh_until':now+timedelta(days=1),'created_at':now,'updated_at':now};x.record_query(r);assert x.preflight_query(source_id='ocpr',subject_id='e',query_type='name',parameters=params).action=='SKIP';assert x.preflight_query(source_id='ocpr',subject_id='e',query_type='name',parameters=params,aliases_changed=True).action=='RUN';x.close()
def test_coverage_dual_metric(tmp_path):
    x=ledger(tmp_path);r=x.calculate_coverage('e','awards',[{'weight':1,'confidence':1},{'weight':0,'confidence':.5,'gap_status':'SOURCE_INACCESSIBLE'}]);assert r['public_data_coverage']==.5;assert r['resolvable_coverage']==1;x.close()
def test_priority_seed_count():
    seeds=json.loads((Path(__file__).parents[2]/'config'/'forensics'/'seed_entity_priority.json').read_text());assert len(seeds)>=60

def test_upsert_reports_unchanged_and_updated(tmp_path):
    x=ledger(tmp_path); now=utcnow()
    r={'source_id':'s','family':'x','endpoint':None,'source_tier':'T1','created_at':now,'updated_at':now}
    assert x.upsert('sources',[r],['source_id']) == {'inserted':1,'updated':0,'unchanged':0}
    assert x.upsert('sources',[r],['source_id']) == {'inserted':0,'updated':0,'unchanged':1}
    r2={**r,'family':'y'}
    assert x.upsert('sources',[r2],['source_id']) == {'inserted':0,'updated':1,'unchanged':0}
    x.close()

def test_retry_window_is_respected(tmp_path):
    x=ledger(tmp_path); params={'q':'jacobs'}; now=utcnow(); qk=query_key('ocpr','e','name',params)
    r={'query_id':'q1','query_key':qk,'source_id':'ocpr','entity_id':'e','project_id':None,'query_type':'name','parameters_json':json.dumps(params),'parameters_hash':'h','started_at':now,'finished_at':now,'status':'BLOCKED_NETWORK','result_count':0,'new_record_count':0,'updated_record_count':0,'null_result':False,'failure_type':'DNS','fallback_route':'BULK','retry_after':now+timedelta(days=1),'fresh_until':None,'created_at':now,'updated_at':now}
    x.record_query(r); d=x.preflight_query(source_id='ocpr',subject_id='e',query_type='name',parameters=params,now=now)
    assert d.action=='SKIP' and d.reason=='retry_window_not_reached'; x.close()
