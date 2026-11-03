"""Scope inference cache entries to the actual RSPN that estimated a factor.

The released IndicatorExpectation hash omits spn identity. Two independently
learned RSPNs can estimate the same marginal differently, so sharing their cached
numeric values makes query results depend on earlier workload order. This local
adapter leaves the original source and factor formulas unchanged. Enter it only
with a fresh ensemble cache; do not mix old/new hash policies in one cache.
"""
from contextlib import contextmanager

from ensemble_compilation.probabilistic_query import IndicatorExpectation


@contextmanager
def model_aware_factor_cache():
    original = IndicatorExpectation.__hash__
    if getattr(original, '_full_model_aware', False):
        yield
        return
    def model_hash(self):
        return hash((original(self), id(self.spn)))
    model_hash._full_model_aware = True
    IndicatorExpectation.__hash__ = model_hash
    try:
        yield
    finally:
        IndicatorExpectation.__hash__ = original
