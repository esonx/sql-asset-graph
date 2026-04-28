from __future__ import annotations

from sql_asset_graph.lineage.contracts import SQLLineageResult, StatementLineageResult

TABLE_USAGE_HEADERS = ["file_name", "access_type", "table_name"]
TABLE_LINEAGE_HEADERS = [
    "file_name",
    "statement_index",
    "statement_type",
    "target_table",
    "source_table",
    "unresolved_dynamic_tables",
]


class LineageAssembler:
    def assemble(self, statements: list[StatementLineageResult]) -> SQLLineageResult:
        return SQLLineageResult.from_statements(statements)

    def to_table_usage_rows(self, file_name: str, result: SQLLineageResult) -> list[dict[str, str]]:
        rows = []
        for table_name in sorted(result.usage_reads):
            rows.append({'file_name': file_name, 'access_type': 'read', 'table_name': table_name})
        for table_name in sorted(result.usage_writes):
            rows.append({'file_name': file_name, 'access_type': 'write', 'table_name': table_name})
        return rows

    def to_table_lineage_rows(self, file_name: str, result: SQLLineageResult) -> list[dict[str, str]]:
        rows = []

        for statement in result.statements:
            for edge in statement.edges:
                rows.append(
                    {
                        'file_name': file_name,
                        'statement_index': str(statement.statement_index),
                        'statement_type': statement.statement_type,
                        'target_table': edge.target_table,
                        'source_table': edge.source_table,
                        'unresolved_dynamic_tables': '',
                    }
                )

            if not statement.edges and statement.target_tables:
                for target_table in sorted(statement.target_tables):
                    rows.append(
                        {
                            'file_name': file_name,
                            'statement_index': str(statement.statement_index),
                            'statement_type': statement.statement_type,
                            'target_table': target_table,
                            'source_table': '',
                            'unresolved_dynamic_tables': '',
                        }
                    )

            for table_name in sorted(statement.unresolved_dynamic_tables):
                rows.append(
                    {
                        'file_name': file_name,
                        'statement_index': str(statement.statement_index),
                        'statement_type': statement.statement_type,
                        'target_table': '',
                        'source_table': '',
                        'unresolved_dynamic_tables': table_name,
                    }
                )

        return rows
