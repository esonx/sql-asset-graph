from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from sql_asset_graph.lineage.backends.hive_native import HiveNativeLineageBackend
from sql_asset_graph.lineage.contracts import (
    LineageParseOptions,
    SQLLineageResult,
    StatementLineageResult,
)


StatementSplitter = Callable[[str], list[str]]


class LineageService:
    def __init__(self, backend=None, statement_splitter: StatementSplitter | None = None):
        self.backend = backend or HiveNativeLineageBackend()
        self.statement_splitter = statement_splitter or self._build_statement_splitter()

    def _build_statement_splitter(self) -> StatementSplitter:
        splitter = getattr(self.backend, 'split_sql_statements', None)
        if callable(splitter):
            return splitter
        return lambda sql_text: [segment.strip() for segment in sql_text.split(';') if segment.strip()]

    @staticmethod
    def _validate_options(options: LineageParseOptions) -> None:
        if options.fragment_mode not in {'compatible', 'strict'}:
            raise ValueError(
                f"Unsupported fragment_mode: {options.fragment_mode!r}. "
                "Expected one of: 'compatible', 'strict'."
            )

    @staticmethod
    def _is_empty_fragment(statement: StatementLineageResult) -> bool:
        return not (
            statement.source_tables
            or statement.target_tables
            or statement.unresolved_dynamic_tables
            or statement.edges
        )

    def _apply_parse_options(
        self,
        statement: StatementLineageResult,
        options: LineageParseOptions,
    ) -> StatementLineageResult | None:
        adjusted = statement

        if not options.keep_unresolved_dynamic_tables and adjusted.unresolved_dynamic_tables:
            adjusted = replace(adjusted, unresolved_dynamic_tables=frozenset())

        if not options.emit_select_only_edges and adjusted.statement_type == 'SELECT':
            adjusted = replace(
                adjusted,
                source_tables=frozenset(),
                target_tables=frozenset(),
                edges=tuple(edge for edge in adjusted.edges if edge.target_table),
            )

        if options.fragment_mode == 'strict' and self._is_empty_fragment(adjusted):
            return None

        return adjusted

    def parse_sql(
        self,
        sql_text: str,
        options: LineageParseOptions | None = None,
    ) -> SQLLineageResult:
        parse_options = options or LineageParseOptions()
        self._validate_options(parse_options)
        statements = []
        for statement_index, statement_sql in enumerate(self.statement_splitter(sql_text), start=1):
            parsed = self.backend.parse_statement(statement_sql, parse_options)
            adjusted = self._apply_parse_options(parsed, parse_options)
            if adjusted is None:
                continue
            statements.append(adjusted.with_statement_index(statement_index))
        return SQLLineageResult.from_statements(statements)

    def parse_file(
        self,
        sql_file: str | Path,
        options: LineageParseOptions | None = None,
    ) -> SQLLineageResult:
        file_path = Path(sql_file)
        return self.parse_sql(file_path.read_text(encoding='utf-8'), options=options)
