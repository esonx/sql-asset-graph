

import re
import csv
from typing import Set, Tuple, List, Dict, Generator, Union
from dataclasses import dataclass, field
from pathlib import Path
import time
import logging
logging.basicConfig(level=logging.INFO)


@dataclass(frozen=True)
class TableLineageEdge:


    statement_index: int
    statement_type: str
    target_table: str
    source_table: str

@dataclass
class SQLConfig:

    default_schemas: List[str] = field(default_factory=list)
    invalid_keywords: Set[str] = field(default_factory=set)

    def __post_init__(self):
        self.default_schemas = ['pth_rmp', 'hds']
        self.invalid_keywords = {
            'select', 'insert', 'create', 'drop', 'alter', 'with', 'as',
            'union', 'intersect', 'except', 'where', 'group', 'order',
            'having', 'limit', 'offset', 'by', 'on', 'using'
        }

class HiveSQLDependencyExtractor:


    def __init__(self, config: SQLConfig):
        self.config = config

        self._write_patterns = [
            r'\bINSERT\s+(?:INTO|OVERWRITE)\s+(?:TABLE\s+)?([^\s\(;]+)(?:\s+PARTITION\s*\([^)]*\))?',
            r'\bCREATE\s+(?:TEMPORARY\s+)?(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(;]+)',
            r'\bDROP\s+(?:TABLE|VIEW)\s+(?:IF\s+EXISTS\s+)?([^\s\(;]+)',
            r'\bALTER\s+TABLE\s+([^\s\(;]+)'
        ]

        self._read_patterns = [
            r'\bFROM\s+(?!\()([^\s\(\);,]+)',
            r'(?:LEFT|RIGHT|INNER|FULL|CROSS|LATERAL)?\s*JOIN\s+([^\s\(\);,]+)',
            r'\bEXISTS\s*\(\s*SELECT[^;]*?FROM\s+([^\s\(\);,]+)',
            r'(?<=\()SELECT[^;]*?FROM\s+([^\s\(\);,]+)',
            r'CREATE\s+(?:TEMPORARY\s+)?VIEW\s+[^\s\(\);]+\s+AS\s+SELECT[^;]*?FROM\s+([^\s\(\);,]+)'
        ]

        self._cte_pattern = (
            r'(?:WITH|,)\s*'
            r'([a-zA-Z0-9_]+)'
            r'(?:\s*\([^)]*\))?\s*'
            r'(?:AS|as)\s*\('
        )

    def _strip_comments(self, sql: str) -> str:

        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*[\s\S]*?\*/', '', sql)
        sql = re.sub(r'^\s*#.*$', '', sql, flags=re.MULTILINE)
        return sql

    def clean_sql(self, sql: str) -> str:

        sql = self._strip_comments(sql)
        return re.sub(r'\s+', ' ', sql).strip()

    def _mark_extracted_query_boundaries(self, sql: str) -> str:

        return re.sub(r'^\s*--\s*End of Query\s*$', ';', sql, flags=re.MULTILINE | re.IGNORECASE)

    def _split_sql_statements(self, sql: str) -> List[str]:

        sql = self._mark_extracted_query_boundaries(sql)
        sql = self._strip_comments(sql)
        statements = []
        current = []
        depth = 0
        quote_char = ''

        for char in sql:
            if quote_char:
                current.append(char)
                if char == quote_char:
                    quote_char = ''
                continue

            if char in ("'", '"'):
                quote_char = char
                current.append(char)
                continue

            if char == '(':
                depth += 1
            elif char == ')' and depth > 0:
                depth -= 1

            if char == ';' and depth == 0:
                statement = ''.join(current).strip()
                if statement:
                    statements.append(statement)
                current = []
                continue

            current.append(char)

        tail = ''.join(current).strip()
        if tail:
            statements.append(tail)

        return statements

    def _detect_statement_type(self, statement: str) -> str:
        stripped_statement = statement.lstrip()

        match = re.match(r'^(INSERT|CREATE|SELECT|DROP|ALTER)\b', stripped_statement, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        if not re.match(r'^WITH\b', stripped_statement, re.IGNORECASE):
            return 'UNKNOWN'

        depth = 0
        quote_char = ''

        for index, char in enumerate(stripped_statement):
            if quote_char:
                if char == quote_char:
                    quote_char = ''
                continue

            if char in ("'", '"'):
                quote_char = char
                continue

            if char == '(':
                depth += 1
                continue

            if char == ')' and depth > 0:
                depth -= 1
                continue

            if depth == 0:
                nested_match = re.match(
                    r'(INSERT|CREATE|SELECT|DROP|ALTER)\b',
                    stripped_statement[index:],
                    re.IGNORECASE,
                )
                if nested_match:
                    return nested_match.group(1).upper()

        return 'UNKNOWN'

    def _is_dynamic_table_name(self, table_name: str) -> bool:
        return '{' in table_name and '}' in table_name

    def _is_malformed_dynamic_table_name(self, table_name: str) -> bool:
        if not self._is_dynamic_table_name(table_name):
            return False
        return bool(re.search(r'\{\s*\}', table_name))

    def _extract_dynamic_tables(self, table_names: Set[str]) -> Set[str]:
        return {table.upper() for table in table_names if self._is_dynamic_table_name(table)}

    def _partition_formal_and_unresolved_tables(self, table_names: Set[str]) -> Tuple[Set[str], Set[str]]:
        formal_tables = set()
        unresolved_tables = set()

        for table_name in table_names:
            if self._is_malformed_dynamic_table_name(table_name):
                unresolved_tables.add(table_name.upper())
                continue
            formal_tables.add(table_name)

        return formal_tables, unresolved_tables

    def _filter_cte_source_tables(self, table_names: Set[str], cte_names: Set[str]) -> Set[str]:

        filtered_tables = set()

        for table_name in table_names:
            table_name_lower = table_name.lower()
            suffix = table_name_lower.split('.', 1)[-1]
            if table_name_lower in cte_names or suffix in cte_names:
                continue
            filtered_tables.add(table_name)

        return filtered_tables

    def extract_statement_lineage(self, sql: str) -> List[Dict[str, Union[int, str, Set[str], List[TableLineageEdge]]]]:

        statements = self._split_sql_statements(sql)
        results = []

        for statement_index, statement in enumerate(statements, start=1):
            read_tables, write_tables = self.extract_tables(statement)
            cte_names = self.extract_cte_names(self.clean_sql(statement))
            read_tables = self._filter_cte_source_tables(read_tables, cte_names)
            statement_type = self._detect_statement_type(statement)

            formal_read_tables, unresolved_read_tables = self._partition_formal_and_unresolved_tables(read_tables)
            formal_write_tables, unresolved_write_tables = self._partition_formal_and_unresolved_tables(write_tables)

            if statement_type == 'SELECT':
                lineage_targets = set()
                lineage_sources = {
                    table_name
                    for table_name in formal_read_tables
                    if not self._is_dynamic_table_name(table_name)
                }
            elif statement_type == 'INSERT':
                lineage_targets = formal_write_tables
                lineage_sources = formal_read_tables
            elif statement_type == 'CREATE' and formal_read_tables and formal_write_tables:
                lineage_targets = formal_write_tables
                lineage_sources = formal_read_tables
            else:
                lineage_targets = set()
                lineage_sources = set()

            if statement_type == 'SELECT':
                edges = [
                    TableLineageEdge(statement_index, statement_type, '', source_table)
                    for source_table in sorted(lineage_sources)
                ]
            else:
                edges = [
                    TableLineageEdge(statement_index, statement_type, target_table, source_table)
                    for target_table in sorted(lineage_targets)
                    for source_table in sorted(lineage_sources)
                ]

            unresolved_dynamic_tables = (
                self._extract_dynamic_tables((read_tables | write_tables) - (lineage_targets | lineage_sources))
                | unresolved_read_tables
                | unresolved_write_tables
            )

            if not edges:
                unresolved_dynamic_tables.update(
                    self._extract_dynamic_tables(lineage_targets | lineage_sources)
                )

            results.append({
                'statement_index': statement_index,
                'statement_type': statement_type,
                'targets': {table.upper() for table in lineage_targets},
                'sources': {table.upper() for table in lineage_sources},
                'edges': edges,
                'unresolved_dynamic_tables': unresolved_dynamic_tables,
            })

        return results

    def extract_table_lineage(self, sql: str) -> Dict[str, Union[int, Set[str], List[TableLineageEdge], List[Dict[str, Union[int, str, Set[str], List[TableLineageEdge]]]]]]:

        statements = self.extract_statement_lineage(sql)
        targets = set()
        sources = set()
        edges = []
        unresolved_dynamic_tables = set()

        for statement in statements:
            targets.update(statement['targets'])
            sources.update(statement['sources'])
            edges.extend(statement['edges'])
            unresolved_dynamic_tables.update(statement['unresolved_dynamic_tables'])

        return {
            'statement_count': len(statements),
            'targets': targets,
            'sources': sources,
            'edges': edges,
            'unresolved_dynamic_tables': unresolved_dynamic_tables,
            'statements': statements,
        }

    def extract_cte_names(self, sql: str) -> Set[str]:

        cte_names = set()
        cleaned_sql = self.clean_sql(sql)

        cte_definitions = re.finditer(
            r'(?:\bWITH\b|,)\s*([a-zA-Z0-9_]+)(?:\s*\([^)]*\))?\s*(?:AS|as)\s*\(',
            cleaned_sql,
            re.IGNORECASE,
        )

        for cte in cte_definitions:
            cte_name = cte.group(1).strip().lower()
            cte_names.add(cte_name)
            for schema in self.config.default_schemas:
                prefixed_name = f"{schema.lower()}.{cte_name}"
                cte_names.add(prefixed_name)

        return cte_names

    def normalize_table_name(self, name: str, sql_content: str) -> str:

        if not name:
            return ''
        name = name.strip().strip('`[]"\'').strip()


        if 'PARTITION' in name.upper():
            name = name.split('PARTITION')[0].strip()
        name = name.split()[0]


        if '.' not in name:
            for schema in self.config.default_schemas:
                if f"{schema}.{name}" in sql_content:
                    return f"{schema}.{name}"
            return f"{self.config.default_schemas[0]}.{name}"
        return name

    def is_valid_name(self, name: str, cte_names: Set[str]) -> bool:

        if not name:
            return False

        name_lower = name.lower()


        if name_lower in cte_names:
            return False


        if '.' in name_lower:
            schema, table = name_lower.split('.', 1)
            if (table in cte_names or
                any(f"{s.lower()}.{table}" in cte_names for s in self.config.default_schemas)):
                return False

        return not any(keyword in name_lower.split('.')
                      for keyword in self.config.invalid_keywords)

    def process_matches(self, sql: str, patterns: List[str],
                       cte_names: Set[str]) -> Set[str]:

        tables = set()
        for pattern in patterns:
            for match in re.finditer(pattern, sql, re.IGNORECASE | re.DOTALL):
                name = self.normalize_table_name(match.group(1), sql)
                if name and self.is_valid_name(name, cte_names):
                    tables.add(name)
        return tables

    def extract_subquery_tables(self, sql: str) -> Set[str]:

        subquery_pattern = r'\(\s*SELECT\s+.*?FROM(.*?)(?:\)|WHERE|\sON\s)'
        matches = re.finditer(subquery_pattern, sql, re.IGNORECASE | re.DOTALL)
        tables = set()

        for match in matches:
            subquery = match.group(1)
            table_matches = re.finditer(r'\b(?:FROM|JOIN)\s+([^\s\(\);,]+)', subquery, re.IGNORECASE)
            for table_match in table_matches:
                table_name = self.normalize_table_name(table_match.group(1), sql)

                if table_name and self.is_valid_name(table_name, set()):
                    tables.add(table_name)
        return tables

    def extract_tables(self, sql: str) -> Tuple[Set[str], Set[str]]:

        sql = self.clean_sql(sql)


        cte_names = self.extract_cte_names(sql)


        view_matches = re.finditer(
            r'CREATE\s+(?:TEMPORARY\s+)?VIEW\s+([^\s\(\);]+)\s+AS\s+(.*?);',
            sql,
            re.IGNORECASE | re.DOTALL
        )

        read_tables = set()
        write_tables = set()

        for match in view_matches:
            view_name = self.normalize_table_name(match.group(1), sql)
            view_query = match.group(2)


            view_read_tables, _ = self._extract_tables_from_sql(view_query, cte_names)
            read_tables.update(view_read_tables)
            if view_name:
                write_tables.add(view_name)


        other_read_tables, other_write_tables = self._extract_tables_from_sql(sql, cte_names)
        read_tables.update(other_read_tables)
        write_tables.update(other_write_tables)


        read_tables = {t for t in read_tables if t.lower() not in cte_names}


        read_tables = {t.upper() for t in read_tables}
        write_tables = {t.upper() for t in write_tables}

        return read_tables, write_tables

    def _extract_tables_from_sql(self, sql: str, cte_names: Set[str]) -> Tuple[Set[str], Set[str]]:

        write_tables = self.process_matches(sql, self._write_patterns, cte_names)
        read_tables = self.process_matches(sql, self._read_patterns, cte_names)


        subquery_tables = self.extract_subquery_tables(sql)
        read_tables.update(subquery_tables)


        read_tables = {t for t in read_tables if t not in write_tables or
                      re.search(rf'\b{t}\b.*\bFROM\b', sql, re.IGNORECASE)}

        return read_tables, write_tables

    def process_directory(self, dir_path: str) -> Generator[Tuple[Path, Set[str], Set[str]], None, None]:


        sql_dir = Path(dir_path)
        if not sql_dir.exists() or not sql_dir.is_dir():
            raise ValueError(f"目录不存在或不是有效目录: {dir_path}")

        for sql_file in sql_dir.glob('**/*.sql'):
            try:
                sql_content = sql_file.read_text(encoding='utf-8')
                read_tables, write_tables = self.extract_tables(sql_content)
                yield sql_file, read_tables, write_tables
            except Exception as e:
                logging.error(f"处理文件 {sql_file} 时出错: {str(e)}")
                continue
