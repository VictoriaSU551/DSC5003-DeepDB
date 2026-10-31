"""Process-local correction of ordered inversion flags at the native boundary.

The original converter expects column indices but its caller passes flags aligned
with an ordered feature_scope. Keep the original files, formulas and fallback
arguments unchanged; translate only the native converter's inversion argument.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
from pathlib import Path


def inverse_feature_indices(feature_scope, inverted_features):
    if len(feature_scope) != len(inverted_features):
        raise ValueError('Feature scope and inversion flag lengths differ')
    return [scope for scope, inverted in zip(feature_scope, inverted_features) if inverted]


def adapter_binding():
    import rspn.code_generation.convert_conditions as original
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return {'mode': 'Ordered boolean flags to actual native feature column indices',
            'adapter_sha256': digest(__file__),
            'original_converter_sha256': digest(original.__file__),
            'original_converter_path': str(Path(original.__file__).resolve()),
            'original_files_changed': False, 'inference_formulas_changed': False}


@contextmanager
def mapped_numeric_inversion():
    """Bind original feature order while calling the unchanged native converter.

Both monkeypatches are confined to this Python process and restored in finally.
ContextVar keeps the ordered call data separate for nested/concurrent contexts.
Recursive Python fallback still receives its original boolean argument list.
"""
    import rspn.rspn as rspn_module
    import rspn.algorithms.expectations as expectation_module
    original_expectation = rspn_module.expectation
    original_convert = expectation_module.convert_range
    current = ContextVar('full_cpp_ordered_inversion', default=None)
    audit = {'converted_calls': 0, 'inverted_calls': 0}

    def bound_expectation(spn, feature_scope, inverted_features, *args, **kwargs):
        inverse_feature_indices(feature_scope, inverted_features)
        token = current.set((tuple(feature_scope), tuple(inverted_features)))
        try:
            return original_expectation(spn, feature_scope, inverted_features, *args, **kwargs)
        finally:
            current.reset(token)

    def convert(relevant_scope, feature_mask, meta_types, conditions, inverted_features):
        ordered = current.get()
        if ordered is None:
            return original_convert(relevant_scope, feature_mask, meta_types, conditions, inverted_features)
        feature_scope, flags = ordered
        if tuple(inverted_features) != flags:
            raise ValueError('Native converter inversion flags differ from expectation boundary')
        if set(feature_scope) != {idx for idx, present in enumerate(feature_mask) if present}:
            raise ValueError('Native feature mask differs from the ordered feature scope')
        indices = inverse_feature_indices(feature_scope, flags)
        audit['converted_calls'] += 1
        audit['inverted_calls'] += bool(indices)
        return original_convert(relevant_scope, feature_mask, meta_types, conditions, indices)

    rspn_module.expectation = bound_expectation
    expectation_module.convert_range = convert
    try:
        yield audit
    finally:
        rspn_module.expectation = original_expectation
        expectation_module.convert_range = original_convert
