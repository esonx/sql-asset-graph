

import csv
import sys
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Set, Tuple
from pathlib import Path


DependencyRow = Mapping[str, str]
DependencyTuple = Tuple[str, str, List[str]]
USAGE_ROW_FIELD_ALIASES = {
    "file_name": ("file_name", "文件名"),
    "access_type": ("access_type", "读写类别"),
    "table_name": ("table_name", "表名"),
}
DEPENDENCY_HEADERS = ["task", "depends_on", "dependency_tables"]


def _get_row_value(row: DependencyRow, *field_names: str) -> str:
    for field_name in field_names:
        value = row.get(field_name)
        if value is not None:
            return str(value)
    return ""


def _normalize_table_name(table_name: str) -> str:
    return str(table_name or '').strip().upper()


def _normalize_file_name(file_name: str) -> str:
    return str(file_name or '').strip()


def _build_dependency_maps(
    usage_rows: Iterable[DependencyRow],
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    table_writers: Dict[str, Set[str]] = defaultdict(set)
    sql_readers: Dict[str, Set[str]] = defaultdict(set)

    for row in usage_rows:
        sql_file = _normalize_file_name(_get_row_value(row, *USAGE_ROW_FIELD_ALIASES["file_name"]))
        operation = _get_row_value(row, *USAGE_ROW_FIELD_ALIASES["access_type"]).strip().lower()
        table = _normalize_table_name(_get_row_value(row, *USAGE_ROW_FIELD_ALIASES["table_name"]))

        if not sql_file or not table:
            continue

        if operation in {'write', '写'}:
            table_writers[table].add(sql_file)
        elif operation in {'read', '读'}:
            sql_readers[sql_file].add(table)

    return table_writers, sql_readers


def _build_dependencies_from_maps(
    table_writers: Mapping[str, Set[str]],
    sql_readers: Mapping[str, Set[str]],
) -> List[DependencyTuple]:
    dependencies_dict: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for sql_file, read_tables in sql_readers.items():
        for table in read_tables:
            for writer_sql in table_writers[table]:
                if writer_sql != sql_file:
                    dependencies_dict[(sql_file, writer_sql)].add(table)

    dependencies = [(reader, writer, sorted(tables))
                   for (reader, writer), tables in dependencies_dict.items()]
    return sorted(dependencies)


def _load_usage_rows(csv_file: str) -> List[DependencyRow]:
    if csv_file == "-":
        return list(csv.DictReader(sys.stdin))
    with open(csv_file, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def extract_sql_dependencies_from_rows(usage_rows: Iterable[DependencyRow]) -> List[DependencyTuple]:

    table_writers, sql_readers = _build_dependency_maps(usage_rows)
    return _build_dependencies_from_maps(table_writers, sql_readers)


def extract_sql_dependencies_from_results(
    file_results: Mapping[str, object] | Iterable[Tuple[str, object]],
) -> List[DependencyTuple]:


    items = file_results.items() if hasattr(file_results, 'items') else file_results
    usage_rows = []

    for file_name, result in items:
        normalized_file_name = _normalize_file_name(file_name)
        usage_reads = getattr(result, 'usage_reads', None)
        usage_writes = getattr(result, 'usage_writes', None)

        if usage_reads is None:
            usage_reads = getattr(result, 'table_reads', ())
        if usage_writes is None:
            usage_writes = getattr(result, 'table_writes', ())

        for table_name in usage_reads or ():
            usage_rows.append({
                'file_name': normalized_file_name,
                'access_type': 'read',
                'table_name': _normalize_table_name(table_name),
            })
        for table_name in usage_writes or ():
            usage_rows.append({
                'file_name': normalized_file_name,
                'access_type': 'write',
                'table_name': _normalize_table_name(table_name),
            })

    return extract_sql_dependencies_from_rows(usage_rows)


def extract_sql_dependencies(csv_file: str) -> List[DependencyTuple]:

    return extract_sql_dependencies_from_rows(_load_usage_rows(csv_file))


def print_dependencies(dependencies: List[DependencyTuple],
                      output_file: str = None) -> None:


    print(",".join(DEPENDENCY_HEADERS))
    for task, dependent_task, tables in dependencies:
        tables_str = ','.join(tables)
        print(f"{task},{dependent_task},{tables_str}")


    if output_file:

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)


        with output_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(DEPENDENCY_HEADERS)
            for task, dependent_task, tables in dependencies:
                writer.writerow([task, dependent_task, ','.join(tables)])
        print(f"\nDependencies have been written to: {output_file}")

def detect_dependency_cycles(dependencies: List[DependencyTuple],
                           ignore_dependencies: List[Dict[str, str]] = None) -> List[List[str]]:


    ignore_set = set()
    if ignore_dependencies:
        ignore_set = {(item['task'], item['depend_on'])
                     for item in ignore_dependencies}


    graph = defaultdict(list)
    nodes = set()
    for task, dependent, _ in dependencies:

        if (task, dependent) in ignore_set:
            continue
        graph[task].append(dependent)
        nodes.add(task)
        nodes.add(dependent)


    def dfs(node: str, path: List[str], visited: Set[str], stack: Set[str]) -> List[List[str]]:


        cycles = []
        if node in stack:

            start_idx = path.index(node)
            cycles.append(path[start_idx:] + [node])
            return cycles

        if node in visited:
            return cycles

        visited.add(node)
        stack.add(node)
        path.append(node)

        for neighbor in graph[node]:
            cycles.extend(dfs(neighbor, path[:], visited, stack))

        stack.remove(node)
        return cycles


    all_cycles = []
    visited = set()

    for node in sorted(nodes):
        if node not in visited:
            cycles = dfs(node, [], visited, set())
            all_cycles.extend(cycles)

    return [cycle for cycle in all_cycles if len(cycle) > 2]

def print_cycles(cycles: List[List[str]], output_file: str = None) -> None:


    if not cycles:
        print("\nNo dependency cycles detected.")
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("No dependency cycles detected.\n")
        return

    print("\nPotential dependency cycles detected:")
    cycle_data = []
    for i, cycle in enumerate(cycles, 1):
        cycle_str = f"Cycle {i}: {' -> '.join(cycle)}"
        print(cycle_str)
        cycle_data.append(cycle_str)


    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w', encoding='utf-8') as f:
            f.write("Potential dependency cycles detected:\n")
            for cycle_str in cycle_data:
                f.write(f"{cycle_str}\n")
        print(f"\nCycle information has been written to: {output_file}")
