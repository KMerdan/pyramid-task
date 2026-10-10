"""Shared legacy runtime exception; no facade import or side effects."""


class PyramidError(RuntimeError):
    # Existing imports and serialized exception references use this public path.
    __module__ = "pyramid_core"
