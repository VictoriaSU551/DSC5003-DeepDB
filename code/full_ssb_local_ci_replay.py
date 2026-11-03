"""Separate ten-million-cap CI replay; the frozen 1M replay is unchanged."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
from full_ssb_replay import atomic, compare_query, coverage, digest, execute_query, read, value_hash
from full_ssb_native_replay import (required_query_files, validate_query_files,
    validate_query_identities, deny_raw_data_access)
from full_ssb_scoped_replay import ScopedReplay, require, THREAD_LIMITS, RTOL, ATOL
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'output/full/ssb/local_sf500_ci10m_replay'
QUERY_NAMES = ['S1.1','S1.2','S1.3','S2.1','S2.2','S2.3','S3.1',
               'S3.2','S3.3','S3.4','S4.1','S4.2','S4.3']
OLD_REPLAY_SHA = 'fc0fcf4045450df9b74e165eb26d0c72d902a2cd9cbc9b85d5b8b78f8ee71fab'
NATIVE_GUARD_SHA = '6c8de16e03a8ba20448121fd4659c092c668d4db0f7214b932a40bf20d30302d'
ORIGINAL_MISMATCH_SHA = '740e525bf5a092f6f28cb1dfc2d3e0226afc206246106fb9ced216faf79aec6e'
EXPECTED_ROWS = dict(lineorder=9996946,dwdate=2556,customer=10000000,part=1800000,supplier=1000000)
METADATA = dict(scope='LOCAL_SSB_10M_CI',author_reproduction_complete=False,
    full_paper_reproduction_complete=False,author_different_groups=1713,
    training_cap_per_table=10000000,actual_training_rows_per_table=EXPECTED_ROWS,
    paper_figure11_training_budget_policy_applied=True,exact10000000_fact_training_rows_claimed=False)
AUXILIARY = ('code/full_ssb_local_ci_replay.py','code/full_ssb_scoped_replay.py')


def source_snapshot():
    from full_ssb_local_ci import verify_local_ci
    require(digest(ROOT/'code/full_ssb_replay.py') == OLD_REPLAY_SHA,
            'frozen replay helper changed')
    require(digest(ROOT/'code/full_ssb_native_replay.py') == NATIVE_GUARD_SHA,
            'frozen inference guard/identity helper changed')
    formal = verify_local_ci()
    require(formal['status'] == 'PASS_READ_ONLY_LOCAL_SSB_10M_CI_WITH_AUTHOR_MISMATCH'
            and all(type(formal[k]) is type(v) and value_hash(formal[k]) == value_hash(v)
                    for k,v in METADATA.items() if k not in ('paper_figure11_training_budget_policy_applied','exact10000000_fact_training_rows_claimed'))
            and type(formal['population_rows']) is int and formal['population_rows'] == 3000028242
            and type(formal['sample_rows']) is int and formal['sample_rows'] == 9996946,
            'complete accepted LOCAL 10M CI model with author mismatch required')
    lineage = formal['lineage']
    require(isinstance(lineage,dict) and all(isinstance(lineage.get(k),dict)
        and type(lineage[k].get('path')) is str and lineage[k]['path']
        and type(lineage[k].get('bytes')) is int and lineage[k]['bytes'] > 0
        and type(lineage[k].get('sha256')) is str and len(lineage[k]['sha256']) == 64
        for k in ('parent_formal','parent_reverse')), 'both accepted parent lineages required')
    auxiliary = formal['dependencies']['auxiliary_sources']
    require(all(auxiliary.get(name) == digest(ROOT/name) for name in AUXILIARY),
            'both current CI replay sources must be frozen in the model plan')
    mismatch = formal['original_mismatch']; target = ROOT/mismatch['path']
    require(target.resolve() == (ROOT/'output/full/results/ssb_native_v2.json').resolve()
            and mismatch['sha256'] == ORIGINAL_MISMATCH_SHA
            and target.stat().st_size == mismatch['bytes'] and digest(target) == ORIGINAL_MISMATCH_SHA,
            'original author population mismatch cannot be hidden or substituted')
    sqls = (ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql').read_text().splitlines()
    validate_query_identities(formal['queries'],sqls,QUERY_NAMES)
    fields = ('verification','verification_seal','published_result','plan','formal_receipt',
        'formal_lifecycle','artifacts','dependencies','model_path','model_sha256','sample_rows',
        'population_rows','evaluation_binding','original_mismatch','lineage')
    snapshot = {name:formal[name] for name in fields}
    snapshot.update(METADATA)
    snapshot.update(frozen_replay_helper_sha256=OLD_REPLAY_SHA,
        frozen_native_guard_sha256=NATIVE_GUARD_SHA,
        replay_sources_sha256={name:digest(ROOT/name) for name in AUXILIARY})
    return snapshot,formal['queries']


def engine():
    return ScopedReplay(ROOT,OUTPUT,__file__,METADATA,
        'PASS_LOCAL_SSB_10M_CI_REVERSE_REPLAY_WITH_AUTHOR_MISMATCH',
        'LOCAL_SSB_10M_CI_REVERSE_REPLAY','DEEPDB_SSB_LOCAL_CI_REPLAY_WORKER',
        source_snapshot,execute_query)


def validate_execution(result): return engine().validate_execution(result)
def binding_for(snapshot): return engine().binding_for(snapshot)
def worker_command(): return engine().worker_command()
def worker_environment_record(): return engine().worker_environment_record()
def worker(): return engine().worker()
def verify(): return engine().verify()
def replay(): return engine().replay()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['replay','worker','verify'])
    report = {'replay':replay,'worker':worker,'verify':verify}[parser.parse_args().action]()
    print({name:report[name] for name in ('status','queries','coverage')})
