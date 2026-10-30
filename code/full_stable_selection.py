"""Canonical traversal for the released greedy selector, as a separate variant.

Original source, candidate scores, component order and factor formulas remain
unchanged. Equal-scoring start/next tables use lexical order. RDC attribute
pairs and summation are canonical. This avoids process-randomized set ordering.
"""
import ast
from contextlib import contextmanager
import inspect
import itertools
import math
import textwrap

import ensemble_compilation.spn_ensemble as original


def canonical_method(method):
    tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    class CanonicalLoops(ast.NodeTransformer):
        def __init__(self):
            self.changed = 0
        def visit_For(self, node):
            node = self.generic_visit(node)
            iterator = node.iter
            table_set = isinstance(iterator, ast.Attribute) and iterator.attr == 'table_set'
            neighbours = isinstance(iterator, ast.Name) and iterator.id == 'possible_neighbours'
            intersection = (isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Attribute)
                            and iterator.func.attr == 'intersection'
                            and isinstance(iterator.func.value, ast.Attribute)
                            and iterator.func.value.attr == 'table_set')
            if table_set or neighbours or intersection:
                node.iter = ast.Call(func=ast.Name(id='sorted', ctx=ast.Load()), args=[iterator], keywords=[])
                self.changed += 1
            return node
    transformer = CanonicalLoops()
    tree = transformer.visit(tree)
    if transformer.changed != 1:
        raise ValueError('released selector AST changed; expected exactly one canonical traversal')
    ast.fix_missing_locations(tree)
    namespace = dict(original.__dict__)
    exec(compile(tree, '<canonical_' + method.__name__ + '>', 'exec'), namespace)
    return namespace[method.__name__]


def canonical_rdc_sum(self, mergeable_tables, query, rdc_attribute_dict):
    columns = sorted({table + '.' + original.infer_column(condition)
                      for table, conditions in query.table_where_condition_dict.items()
                      if table in mergeable_tables for condition in conditions})
    return math.fsum(rdc_attribute_dict[pair] for pair in itertools.combinations(columns, 2)
                     if rdc_attribute_dict.get(pair) is not None)


@contextmanager
def canonical_greedy_selection():
    cls = original.SPNEnsemble
    names = ['_greedily_select_first_cardinality_spn', '_greedily_select_next_table', '_possible_first_spns']
    saved = {name: getattr(cls, name) for name in names + ['merged_rdc_sum']}
    try:
        for name in names:
            setattr(cls, name, canonical_method(saved[name]))
        cls.merged_rdc_sum = canonical_rdc_sum
        yield
    finally:
        for name, method in saved.items():
            setattr(cls, name, method)
