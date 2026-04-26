from __future__ import annotations

from sql_asset_graph.lineage.contracts import LineageParseOptions, StatementLineageResult


class SqllineageLineageBackend:
    def parse_statement(self, sql: str, options: LineageParseOptions) -> StatementLineageResult:
        del sql, options
        raise NotImplementedError('sqllineage adapter is reserved for a later PRD004 phase')