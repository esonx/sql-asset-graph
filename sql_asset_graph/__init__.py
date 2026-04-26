

from importlib import import_module

from . import dependency, extraction, lineage, preprocessing, utils

__all__ = [
 'main',
 'dependency',
 'extraction',
 'preprocessing',
 'utils',
]


def __getattr__(name):
	if name == 'main':
		return import_module('sql_asset_graph.main')
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
