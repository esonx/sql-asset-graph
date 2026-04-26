from __future__ import annotations

from typing import Protocol

from sql_asset_graph.lineage.contracts import LineageParseOptions, StatementLineageResult


class LineageBackend(Protocol):
    def parse_statement(self, sql: str, options: LineageParseOptions) -> StatementLineageResult:
        ...