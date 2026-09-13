"""Renderer registry.

Profiles name a renderer with a plain string key. Profile data never carries a
module path or anything else importable -- lookup is this dict and nothing else.
"""

from qrgen.renderers.standard import render as render_standard

REGISTRY = {
    "standard": render_standard,
}


def get(name):
    try:
        return REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown renderer {name!r}; known: {sorted(REGISTRY)}")
