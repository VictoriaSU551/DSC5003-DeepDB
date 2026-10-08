"""Check dataset row counts and independently recompute three JOB-light counts."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from schemas.imdb.schema import gen_job_light_imdb_schema

ROOT = Path(__file__).resolve().parents[1]


def main():
    schema = gen_job_light_imdb_schema(str(ROOT / 'data/imdb/{}.csv'))
    row_counts = {}
    # Read raw CSVs in bounded chunks, independently of HDF/model preparation.
    for table in schema.tables:
        count = 0
        for chunk in pd.read_csv(table.csv_file_location, header=None, usecols=[0], escapechar='\\',
                                 encoding='utf-8', chunksize=1000000):
            count += len(chunk)
        row_counts[table.table_name] = count
        print(table.table_name, count, flush=True)

    def read(name, indices, columns):
        frame = pd.read_csv(ROOT / 'data/imdb' / (name + '.csv'), header=None, usecols=indices,
                            escapechar='\\', encoding='utf-8')
        frame.columns = columns
        return frame

    title = read('title', [0, 4], ['movie_id', 'production_year']).set_index('movie_id')
    companies = read('movie_companies', [1, 3], ['movie_id', 'company_type_id'])
    info = read('movie_info_idx', [1, 2], ['movie_id', 'info_type_id'])
    companies = companies.loc[companies.company_type_id == 2].groupby('movie_id').size()
    truth = pd.read_csv(ROOT / 'code/benchmarks/job-light/sql/job_light_true_cardinalities.csv')
    checks = []
    for query_no, info_type, lower, upper in [(0, 112, None, None), (1, 113, 2005, 2010), (2, 112, 2010, None)]:
        counts = info.loc[info.info_type_id == info_type].groupby('movie_id').size()
        joined = title.join(companies.rename('companies')).join(counts.rename('info'))
        if lower is not None:
            joined = joined.loc[joined.production_year > lower]
        if upper is not None:
            joined = joined.loc[joined.production_year < upper]
        actual = int((joined.companies.fillna(0) * joined['info'].fillna(0)).sum())
        expected = int(truth.loc[truth.query_no == query_no, 'cardinality_true'].iloc[0])
        assert actual == expected, (query_no, actual, expected)
        checks.append(dict(query_no=query_no, actual=actual, expected=expected))
    result = dict(status='PASS', row_counts=row_counts, full_tables=True,
                  raw_data_ground_truth_checks=checks,
                  note='Three counts recomputed directly from raw CSVs. Remaining official truths not independently recomputed.')
    path = ROOT / 'output/results/data_audit.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
