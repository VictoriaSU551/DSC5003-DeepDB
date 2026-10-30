"""Derived figures for the distinct 10M/table-cap local CI experiment."""
from full_ssb_local_tables import main as build


def configuration():
    # Lazy: importing a table validator never imports or executes CI training.
    def verify():
        from full_ssb_local_ci_replay import verify as accepted_replay
        return accepted_replay()
    return dict(stage='LOCAL_SSB_SF500_SINGLE_10M_CI',scope='LOCAL_SSB_10M_CI',
        cap=10000000,training_rows=dict(lineorder=9996946,dwdate=2556,customer=10000000,part=1800000,supplier=1000000),
        verify=verify,result='ssb_local_sf500_ci10m.json',prefix='aqp_ssb_local_ci10m_',
        pointer='ssb_local_ci10m_tables_latest.json',policy_applied=True,
        normalizer_scope='Original retained n/p fact normalizer and full dimension normalizers; separate10M/table-cap models',
        helpers=['code/full_ssb_local_ci_tables.py','code/full_ssb_local_ci_replay.py',
                 'code/full_ssb_scoped_replay.py','code/full_ssb_local_ci.py',
                 'code/full_ssb_local_stage_validation.py','code/full_ssb_local_ci_run.py'])


if __name__=='__main__':build(configuration())
