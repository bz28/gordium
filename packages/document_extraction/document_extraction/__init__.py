"""Gordium document extraction: source PDFs -> text with page and position (step 2)."""

from .extract import extract, to_jsonl

__all__ = ["extract", "to_jsonl"]
