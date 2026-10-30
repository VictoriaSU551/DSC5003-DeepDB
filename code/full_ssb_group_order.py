"""A separate SSB evaluation variant with a deterministic GROUP BY prototype.

The release builds its prototype from the first decoded group, after converting
groups through a set. Different hash seeds can therefore select different
cardinality factorizations and CI variances. This adapter only permutes paired
technical/decoded rows. Models, group membership, columns, factor scores, and
point/variance formulas are unchanged. Historical results remain separate.
"""
from contextlib import contextmanager
from fractions import Fraction
import math
from numbers import Integral, Real


def scalar_order_key(value):
    if value is None:return (0,0)
    if isinstance(value,bool):return (1,int(value))
    if isinstance(value,Integral):return (2,Fraction(int(value)))
    if isinstance(value,Real):
        number=float(value)
        if not math.isfinite(number):raise ValueError('Nonfinite decoded group key')
        return (2,Fraction.from_float(number))
    if isinstance(value,str):return (3,value)
    raise ValueError('Unsupported decoded SQL group key type: '+type(value).__name__)


def order_group_pairs(scopes,technical,decoded):
    if not isinstance(technical,(list,tuple)) or not isinstance(decoded,(list,tuple)) or len(technical)!=len(decoded):
        raise ValueError('Aligned technical and decoded group rows required')
    keys=[]
    for raw,label in zip(technical,decoded):
        if not isinstance(raw,(list,tuple)) or not isinstance(label,(list,tuple)) or len(raw)!=len(scopes) or len(label)!=len(scopes):
            raise ValueError('Group row widths must match unchanged scope columns')
        keys.append(tuple(scalar_order_key(value) for value in label))
    if len(set(keys))!=len(keys):raise ValueError('Duplicate decoded SQL group identity')
    order=sorted(range(len(keys)),key=keys.__getitem__)
    return scopes,[technical[i] for i in order],[decoded[i] for i in order]


@contextmanager
def canonical_group_order(module=None):
    if module is None:
        import ensemble_compilation.spn_ensemble as module
    cls=module.SPNEnsemble;original=cls._evaluate_group_by_spn_ensembles
    def ordered(self,query):
        return order_group_pairs(*original(self,query))
    cls._evaluate_group_by_spn_ensembles=ordered
    try:yield
    finally:cls._evaluate_group_by_spn_ensembles=original
