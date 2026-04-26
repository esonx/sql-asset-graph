

import csv
import sys
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

CYCLE_HEADERS = ["cycle_id", "cycle_length", "sequence_index", "table_name"]

LINEAGE_ROW_FIELD_ALIASES = {
    "target_table": ("target_table", "目标表"),
    "source_table": ("source_table", "来源表"),
}


def _get_row_value(row: dict[str, str], *field_names: str) -> str:
    for field_name in field_names:
        value = row.get(field_name)
        if value is not None:
            return str(value)
    return ""


def _normalize_table_name(table_name: str) -> str:
    return (table_name or '').strip().upper()


def _is_malformed_dynamic_table_name(table_name: str) -> bool:
    normalized = _normalize_table_name(table_name)
    return normalized in {'{}', '{}.{}'}


def _is_formal_lineage_table(table_name: str) -> bool:
    normalized = _normalize_table_name(table_name)
    return bool(normalized) and not _is_malformed_dynamic_table_name(normalized)


def _load_formal_lineage_edges(csv_file: str) -> List[Tuple[str, str]]:
    edges: List[Tuple[str, str]] = []
    if csv_file == "-":
        file_obj = sys.stdin
        reader = csv.DictReader(file_obj)
        for row in reader:
            target_table = _normalize_table_name(_get_row_value(row, *LINEAGE_ROW_FIELD_ALIASES["target_table"]))
            source_table = _normalize_table_name(_get_row_value(row, *LINEAGE_ROW_FIELD_ALIASES["source_table"]))
            if not _is_formal_lineage_table(target_table):
                continue
            if not _is_formal_lineage_table(source_table):
                continue
            edges.append((target_table, source_table))
        return edges

    with open(csv_file, 'r', encoding='utf-8') as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            target_table = _normalize_table_name(_get_row_value(row, *LINEAGE_ROW_FIELD_ALIASES["target_table"]))
            source_table = _normalize_table_name(_get_row_value(row, *LINEAGE_ROW_FIELD_ALIASES["source_table"]))
            if not _is_formal_lineage_table(target_table):
                continue
            if not _is_formal_lineage_table(source_table):
                continue
            edges.append((target_table, source_table))
    return edges


def _normalize_edge_pair(edge) -> Tuple[str, str]:
    if isinstance(edge, tuple) and len(edge) >= 2:
        return _normalize_table_name(edge[0]), _normalize_table_name(edge[1])

    return (
        _normalize_table_name(getattr(edge, 'target_table', '')),
        _normalize_table_name(getattr(edge, 'source_table', '')),
    )


def build_table_lineage_graph_from_edges(edges: Iterable[Tuple[str, str]]) -> Dict[str, Dict[str, Set[str]]]:
    upstream_map: Dict[str, Set[str]] = defaultdict(set)
    downstream_map: Dict[str, Set[str]] = defaultdict(set)

    for edge in edges:
        target_table, source_table = _normalize_edge_pair(edge)
        if not _is_formal_lineage_table(target_table):
            continue
        if not _is_formal_lineage_table(source_table):
            continue

        upstream_map[target_table].add(source_table)
        downstream_map[source_table].add(target_table)

    return {
        'upstream_map': dict(upstream_map),
        'downstream_map': dict(downstream_map),
    }


def build_table_lineage_graph_from_result(result) -> Dict[str, Dict[str, Set[str]]]:
    return build_table_lineage_graph_from_edges(getattr(result, 'table_edges', ()))


def build_table_lineage_graph(csv_file: str) -> Dict[str, Dict[str, Set[str]]]:

    return build_table_lineage_graph_from_edges(_load_formal_lineage_edges(csv_file))


def get_direct_upstream_tables(csv_file: str, target_table: str) -> List[str]:
    graph = build_table_lineage_graph(csv_file)
    return sorted(graph['upstream_map'].get(_normalize_table_name(target_table), set()))


def get_direct_downstream_tables(csv_file: str, source_table: str) -> List[str]:
    graph = build_table_lineage_graph(csv_file)
    return sorted(graph['downstream_map'].get(_normalize_table_name(source_table), set()))


def _normalize_cycle(cycle: List[str]) -> Tuple[str, ...]:
    ring = cycle[:-1]
    if not ring:
        return tuple(cycle)

    start_index = min(range(len(ring)), key=lambda index: ring[index])
    rotated = ring[start_index:] + ring[:start_index]
    rotated.append(rotated[0])
    return tuple(rotated)


def detect_table_lineage_cycles(csv_file: str) -> List[List[str]]:

    graph = build_table_lineage_graph(csv_file)['upstream_map']
    nodes = sorted(set(graph.keys()) | {neighbor for neighbors in graph.values() for neighbor in neighbors})

    cycles: Set[Tuple[str, ...]] = set()

    def dfs(node: str, path: List[str], path_set: Set[str]) -> None:
        path.append(node)
        path_set.add(node)

        for neighbor in sorted(graph.get(node, set())):
            if neighbor in path_set:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                if len(cycle) > 2:
                    cycles.add(_normalize_cycle(cycle))
                continue
            dfs(neighbor, path[:], set(path_set))

    for node in nodes:
        dfs(node, [], set())

    return [list(cycle) for cycle in sorted(cycles)]


def detect_table_lineage_cycles_from_result(result) -> List[List[str]]:

    graph = build_table_lineage_graph_from_result(result)['upstream_map']
    nodes = sorted(set(graph.keys()) | {neighbor for neighbors in graph.values() for neighbor in neighbors})

    cycles: Set[Tuple[str, ...]] = set()

    def dfs(node: str, path: List[str], path_set: Set[str]) -> None:
        path.append(node)
        path_set.add(node)

        for neighbor in sorted(graph.get(node, set())):
            if neighbor in path_set:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                if len(cycle) > 2:
                    cycles.add(_normalize_cycle(cycle))
                continue
            dfs(neighbor, path[:], set(path_set))

    for node in nodes:
        dfs(node, [], set())

    return [list(cycle) for cycle in sorted(cycles)]


def to_cycle_rows(cycles: List[List[str]]) -> List[dict[str, str]]:
    rows: List[dict[str, str]] = []
    for cycle_index, cycle in enumerate(cycles, 1):
        cycle_length = str(max(len(cycle) - 1, 0))
        for sequence_index, table_name in enumerate(cycle, 1):
            rows.append(
                {
                    "cycle_id": str(cycle_index),
                    "cycle_length": cycle_length,
                    "sequence_index": str(sequence_index),
                    "table_name": table_name,
                }
            )
    return rows
