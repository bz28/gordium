"""Address in, site facts out: see README.md. Shared here: geometry and http; each place's own lookup is in
adapters/<name>/, chosen by its settings (adapter(place))."""

from .adapters import adapter

__all__ = ["adapter"]
