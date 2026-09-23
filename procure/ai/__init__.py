"""Deterministic explanation interfaces."""

from procure.ai.render import PLACEHOLDERS, render_template
from procure.ai.template import build_sentences, build_template_explanation

__all__ = [
    "PLACEHOLDERS",
    "build_sentences",
    "build_template_explanation",
    "render_template",
]
