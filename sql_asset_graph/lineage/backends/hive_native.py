from __future__ import annotations

from sql_asset_graph.dependency.hive_sql_parser import HiveSQLDependencyExtractor, SQLConfig
from sql_asset_graph.lineage.contracts import (
    LineageParseOptions,
    StatementLineageResult,
    TableLineageEdge,
)


class HiveNativeLineageBackend:
    def __init__(self, extractor: HiveSQLDependencyExtractor | None = None):
        self.extractor = extractor or HiveSQLDependencyExtractor(SQLConfig())

    def split_sql_statements(self, sql_text: str) -> list[str]:
        return self.extractor._split_sql_statements(sql_text)

    def parse_statement(self, sql: str, options: LineageParseOptions) -> StatementLineageResult:
        del options

        read_tables, write_tables = self.extractor.extract_tables(sql)
        statements = self.extractor.extract_statement_lineage(sql)
        if not statements:
            return StatementLineageResult(
                statement_index=1,
                statement_type='UNKNOWN',
                read_tables=read_tables,
                write_tables=write_tables,
            )

        statement = statements[0]
        return StatementLineageResult(
            statement_index=statement['statement_index'],
            statement_type=statement['statement_type'],
            read_tables=read_tables,
            write_tables=write_tables,
            source_tables=statement['sources'],
            target_tables=statement['targets'],
            unresolved_dynamic_tables=statement['unresolved_dynamic_tables'],
            edges=tuple(
                TableLineageEdge(
                    statement_index=edge.statement_index,
                    statement_type=edge.statement_type,
                    target_table=edge.target_table,
                    source_table=edge.source_table,
                )
                for edge in statement['edges']
            ),
        )