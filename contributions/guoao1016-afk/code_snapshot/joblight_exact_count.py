"""Exact multiplicity aggregation for validated inner star COUNT(*) queries.

This rewrites SQL, not data or reference counts. Each matching title contributes
the product of its filtered child-row counts, with zero contributions excluded
by the original inner-join semantics. No independence assumption is involved.
"""
import re

def factorized_count_sql(query):
    parsed=re.fullmatch(r'\s*SELECT\s+COUNT\(\*\)\s+FROM\s+(.+?)\s+WHERE\s+(.+?)\s*;?\s*',query,re.I|re.S)
    if not parsed:raise ValueError('Only ungrouped SELECT COUNT(*) with WHERE is supported')
    relations={}
    for part in parsed.group(1).split(','):
        m=re.fullmatch(r'\s*([a-z_]+)\s+([a-z_]+)\s*',part,re.I)
        if not m or m.group(2) in relations:raise ValueError('Invalid or repeated alias')
        table,alias=m.groups()
        if table not in {'title','movie_info','movie_info_idx','movie_keyword','movie_companies','cast_info'}:raise ValueError('Unsupported table')
        relations[alias]=table
    anchors=[a for a,t in relations.items() if t=='title']
    if len(anchors)!=1:raise ValueError('Exactly one title anchor is required')
    anchor=anchors[0];filters={a:[] for a in relations};joins=[]
    for condition in re.split(r'\s+AND\s+',parsed.group(2).rstrip(';').strip(),flags=re.I):
        equality=re.fullmatch(r'\s*([a-z_]+)\.(id|movie_id)\s*=\s*([a-z_]+)\.(id|movie_id)\s*',condition,re.I)
        if equality:
            a,col,b,other=equality.groups()
            if a==anchor and col=='id' and b in relations and b!=anchor and other=='movie_id':joins.append(b)
            elif b==anchor and other=='id' and a in relations and a!=anchor and col=='movie_id':joins.append(a)
            else:raise ValueError('Join is not a title.id-to-child.movie_id star edge')
        else:
            predicate=re.fullmatch(r'\s*([a-z_]+)\.([a-z_]+)\s*(<=|>=|<>|=|<|>)\s*(-?\d+(?:\.\d+)?)\s*',condition,re.I)
            if not predicate or predicate.group(1) not in relations:raise ValueError('Only numeric single-table predicates are supported')
            filters[predicate.group(1)].append(condition.strip())
    children=[a for a in relations if a!=anchor]
    if sorted(joins)!=sorted(children):raise ValueError('Each child must have exactly one anchor join')
    def where(alias):return ' WHERE '+' AND '.join(filters[alias]) if filters[alias] else ''
    ctes=['exact_titles AS (SELECT %s.id FROM title %s%s)'%(anchor,anchor,where(anchor))]
    for i,alias in enumerate(children):
        ctes.append('exact_g%d AS (SELECT %s.movie_id, COUNT(*)::numeric AS n FROM %s %s%s GROUP BY %s.movie_id)'%(i,alias,relations[alias],alias,where(alias),alias))
    product=' * '.join('exact_g%d.n'%i for i in range(len(children))) or '1::numeric'
    joinsql=' '.join('JOIN exact_g%d ON exact_g%d.movie_id=exact_t.id'%(i,i) for i in range(len(children)))
    return 'WITH '+',\n'.join(ctes)+'\nSELECT COALESCE(SUM('+product+'),0) FROM exact_titles exact_t '+joinsql+';'
