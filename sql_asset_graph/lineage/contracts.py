from __future__ import annotations

from dataclasses import dataclass, field


def _normalize_name(value: str) -> str:
    return str(value or '').strip().upper()


def _normalize_names(values) -> frozenset[str]:
    return frozenset(_normalize_name(value) for value in values if _normalize_name(value))


@dataclass(frozen=True)
class TableLineageEdge:
    statement_index: int
    statement_type: str
    target_table: str
    source_table: str

    def __post_init__(self):
        object.__setattr__(self, 'statement_type', _normalize_name(self.statement_type))
        object.__setattr__(self, 'target_table', _normalize_name(self.target_table))
        object.__setattr__(self, 'source_table', _normalize_name(self.source_table))

    def with_statement_index(self, statement_index: int) -> 'TableLineageEdge':
        return TableLineageEdge(
            statement_index=statement_index,
            statement_type=self.statement_type,
            target_table=self.target_table,
            source_table=self.source_table,
        )


@dataclass(frozen=True)
class StatementLineageResult:
    statement_index: int
    statement_type: str
    read_tables: frozenset[str] = field(default_factory=frozenset)
    write_tables: frozenset[str] = field(default_factory=frozenset)
    source_tables: frozenset[str] = field(default_factory=frozenset)
    target_tables: frozenset[str] = field(default_factory=frozenset)
    unresolved_dynamic_tables: frozenset[str] = field(default_factory=frozenset)
    edges: tuple[TableLineageEdge, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, 'statement_type', _normalize_name(self.statement_type))
        normalized_reads = _normalize_names(self.read_tables) or _normalize_names(self.source_tables)
        normalized_writes = _normalize_names(self.write_tables) or _normalize_names(self.target_tables)
        object.__setattr__(self, 'read_tables', normalized_reads)
        object.__setattr__(self, 'write_tables', normalized_writes)
        object.__setattr__(self, 'source_tables', _normalize_names(self.source_tables))
        object.__setattr__(self, 'target_tables', _normalize_names(self.target_tables))
        object.__setattr__(
            self,
            'unresolved_dynamic_tables',
            _normalize_names(self.unresolved_dynamic_tables),
        )
        object.__setattr__(self, 'edges', tuple(self.edges))

    def with_statement_index(self, statement_index: int) -> 'StatementLineageResult':
        return StatementLineageResult(
            statement_index=statement_index,
            statement_type=self.statement_type,
            read_tables=self.read_tables,
            write_tables=self.write_tables,
            source_tables=self.source_tables,
            target_tables=self.target_tables,
            unresolved_dynamic_tables=self.unresolved_dynamic_tables,
            edges=tuple(edge.with_statement_index(statement_index) for edge in self.edges),
        )


@dataclass(frozen=True)
class SQLLineageResult:
    statements: tuple[StatementLineageResult, ...] = field(default_factory=tuple)
    table_edges: tuple[TableLineageEdge, ...] = field(default_factory=tuple)
    table_reads: frozenset[str] = field(default_factory=frozenset)
    table_writes: frozenset[str] = field(default_factory=frozenset)
    usage_reads: frozenset[str] = field(default_factory=frozenset)
    usage_writes: frozenset[str] = field(default_factory=frozenset)
    unresolved_dynamic_tables: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_statements(cls, statements: list[StatementLineageResult]) -> 'SQLLineageResult':
        normalized = tuple(statements)
        return cls(
            statements=normalized,
            table_edges=tuple(edge for statement in normalized for edge in statement.edges),
            table_reads=frozenset(
                table for statement in normalized for table in statement.source_tables
            ),
            table_writes=frozenset(
                table for statement in normalized for table in statement.target_tables
            ),
            usage_reads=frozenset(
                table for statement in normalized for table in statement.read_tables
            ),
            usage_writes=frozenset(
                table for statement in normalized for table in statement.write_tables
            ),
            unresolved_dynamic_tables=frozenset(
                table
                for statement in normalized
                for table in statement.unresolved_dynamic_tables
            ),
        )


@dataclass(frozen=True)
class LineageParseOptions:
    dialect: str = 'hive'
    keep_unresolved_dynamic_tables: bool = True
    emit_select_only_edges: bool = True
    fragment_mode: str = 'compatible'