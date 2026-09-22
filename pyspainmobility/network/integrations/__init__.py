"""Optional adapters from the canonical sparse network representation."""

from .networkx import to_networkx
from .infomap import run_infomap, to_infomap

__all__ = ["run_infomap", "to_infomap", "to_networkx"]
