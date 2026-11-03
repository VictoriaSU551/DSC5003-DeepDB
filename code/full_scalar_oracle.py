"""Independent scalar-oracle uniform title-key variant; not author configuration.

The prediction API accepts only single-table counts. It never reads evaluation
labels, model files, CSV data or a database. Fractions preserve raw zeros and
integer oracle values exactly; evaluation flooring belongs to a separate stage.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
QUERY_FILE = 'code/benchmarks/job-light/sql/job_light_queries.sql'
QUERY_SHA = 'e61da91710ce62d3669be70a8ded2499c6de1d759fcfac9a954b939465e76fdb'
VARIANT = 'LOCAL_SCALAR_ORACLE_UNIFORM_TITLE_KEY_V1'
EXPECTED_ROWS = dict(title=2528312, movie_info_idx=1380035, movie_info=14835720,
                     cast_info=36244344, movie_keyword=4523930, movie_companies=2609129)
COLUMNS = {
    'title': {'id', 'kind_id', 'production_year', 'imdb_id', 'episode_of_id', 'season_nr', 'episode_nr'},
    'movie_info_idx': {'id', 'movie_id', 'info_type_id'},
    'movie_info': {'id', 'movie_id', 'info_type_id'},
    'cast_info': {'id', 'movie_id', 'person_id', 'person_role_id', 'nr_order', 'role_id'},
    'movie_keyword': {'id', 'movie_id', 'keyword_id'},
    'movie_companies': {'id', 'movie_id', 'company_id', 'company_type_id'},
}
SCOPE = dict(method=VARIANT, author_method_configuration_identified=False,
             author_Perfect_Selectivities_reproduction_complete=False,
             full_paper_reproduction_complete=False,
             scalar_single_table_oracle=True, cross_table_truth_used_for_prediction=False,
             original_csv_current_database_full_value_identity_claimed=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def object_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def integer(value, name='count'):
    require(type(value) is int and value >= 0, 'Nonnegative exact integer required: ' + name)
    return value


def predicate(table, conditions):
    terms = [{'column': c, 'operator': op, 'value': v} for c,op,v in conditions]
    identity = dict(table=table, conjunction=sorted(conditions))
    return dict(id=object_hash(identity), table=table, conditions=terms)


def parse_query(sql, query_no):
    require(type(query_no) is int and query_no >= 0 and type(sql) is str, 'Invalid query identity')
    match = re.fullmatch(r'\s*SELECT\s+COUNT\(\*\)\s+FROM\s+(.+?)\s+WHERE\s+(.+?)\s*;\s*', sql, re.I)
    require(match is not None, 'Only the registered COUNT/star/conjunction SQL grammar is supported')
    aliases = {}
    for relation in match[1].split(','):
        item = re.fullmatch(r'\s*([a-z_]+)\s+([a-z_]+)\s*', relation)
        require(item is not None and item[1] in COLUMNS and item[2] not in aliases, 'Unsupported table or alias')
        aliases[item[2]] = item[1]
    require(2 <= len(aliases) <= 5 and len(set(aliases.values())) == len(aliases)
            and 'title' in aliases.values(), 'A unique title-centred star is required')
    conditions = {t: [] for t in aliases.values()}
    joins = []
    for term in re.split(r'\s+AND\s+', match[2], flags=re.I):
        join = re.fullmatch(r'\s*([a-z_]+)\.([a-z_]+)\s*=\s*([a-z_]+)\.([a-z_]+)\s*', term)
        if join:
            a,c,b,d = join.groups()
            require(a in aliases and b in aliases, 'Unknown join alias')
            ends = {(aliases[a], c), (aliases[b], d)}
            child = aliases[b] if aliases[a] == 'title' else aliases[a]
            require(child != 'title' and ends == {('title', 'id'), (child, 'movie_id')}, 'Non-star join rejected')
            joins.append(child)
        else:
            filt = re.fullmatch(r'\s*([a-z_]+)\.([a-z_]+)\s*(<=|>=|!=|=|<|>)\s*(-?\d+)\s*', term)
            require(filt is not None and filt[1] in aliases, 'Unsupported filter expression')
            table = aliases[filt[1]]
            require(filt[2] in COLUMNS[table], 'Unsupported filter column')
            conditions[table].append((filt[2], filt[3], int(filt[4])))
    require(len(joins) == len(aliases)-1 and len(set(joins)) == len(joins)
            and set(joins) == set(aliases.values())-{'title'}, 'Missing or duplicate join predicate')
    return dict(query_no=query_no, sql=sql.strip(), tables=sorted(aliases.values()),
                predicates=[predicate(t, conditions[t]) for t in sorted(conditions)])


def contract_from_queries(queries):
    ids = [q['query_no'] for q in queries]
    require(ids == list(range(len(queries))), 'Complete ordered unique query identities required')
    predicates = {}
    for q in queries:
        for p in q['predicates']:
            predicates.setdefault(p['id'], p)
    return dict(variant=VARIANT, queries=queries,
                predicates=[predicates[k] for k in sorted(predicates)],
                tables=sorted({p['table'] for p in predicates.values()}))


def workload(path=None):
    path = ROOT/QUERY_FILE if path is None else Path(path)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == QUERY_SHA, 'Pinned workload bytes changed')
    lines = [line.strip() for line in raw.decode('utf-8').splitlines() if line.strip()]
    require(len(lines) == 70, 'Exactly 70 workload queries required')
    result = contract_from_queries([parse_query(sql, i) for i,sql in enumerate(lines)])
    require(len(result['predicates']) == 50 and result['tables'] == sorted(COLUMNS), 'Fixed 70/50 workload grid changed')
    return result


def count_statements(contract):
    output = {}
    for table in contract['tables']:
        expressions, parameters, ids = [], [], []
        for p in contract['predicates']:
            if p['table'] != table:
                continue
            clauses = []
            for term in p['conditions']:
                clauses.append('"{}" {} %s'.format(term['column'], term['operator']))
                parameters.append(term['value'])
            expressions.append('COUNT(*) FILTER (WHERE {})'.format(' AND '.join(clauses) or 'TRUE'))
            ids.append(p['id'])
        output[table] = dict(sql='SELECT COUNT(*), COUNT(DISTINCT "id"), COUNT(*) FILTER (WHERE "id" IS NULL), '
                             + ', '.join(expressions) + ' FROM public."' + table + '"',
                             parameters=parameters, predicate_ids=ids)
    return output


def uniform_estimate(query, scalar_counts, title_population):
    integer(title_population, 'title population')
    require(title_population > 0, 'Empty title population cannot define a uniform key domain')
    result = Fraction(1)
    for p in query['predicates']:
        require(p['id'] in scalar_counts, 'Missing scalar oracle')
        value = integer(scalar_counts[p['id']])
        if p['table'] == 'title':
            require(value <= title_population, 'Filtered title count exceeds its population')
            result *= value
        else:
            result *= Fraction(value, title_population)
    return result


def rational_record(value):
    require(isinstance(value, Fraction) and value >= 0, 'Nonnegative exact Fraction required')
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def validate_counts(contract, counts, population, assumptions):
    require(set(counts) == {p['id'] for p in contract['predicates']}, 'Complete exact scalar oracle set required')
    require(population == EXPECTED_ROWS and all(type(n) is int for n in population.values()), 'Six registered population row counts required')
    require(set(assumptions) == set(population), 'Complete primary/foreign key assumptions required')
    for table,n in population.items():
        a = assumptions[table]
        require(set(a) == {'rows','distinct_ids','null_ids','null_movie_ids','orphan_movie_ids'}, 'Assumption receipt schema changed')
        for value in a.values():
            integer(value, 'assumption')
        require(a['rows'] == a['distinct_ids'] == n and a['null_ids'] == a['null_movie_ids'] == a['orphan_movie_ids'] == 0,
                'Unique non-NULL PK and complete non-NULL title FK domain required')
    for p in contract['predicates']:
        n = integer(counts[p['id']])
        require(n <= population[p['table']], 'Oracle count exceeds its table')
        if not p['conditions']:
            require(n == population[p['table']], 'Unfiltered scalar disagrees with table population')


def predictions(contract, counts, population, assumptions):
    validate_counts(contract, counts, population, assumptions)
    return [dict(query_no=q['query_no'], sql=q['sql'],
                 estimate=rational_record(uniform_estimate(q, counts, population['title'])))
            for q in contract['queries']]
