

import sys
import argparse
import csv
import json
import logging
from pathlib import Path


def _resolve_cli_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _write_csv_rows(output_target: str, headers: list[str], rows: list[list[str]]) -> None:
    if output_target == "-":
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(rows)
        return

    output_path = Path(output_target)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', newline='', encoding='utf-8') as output_handle:
        writer = csv.writer(output_handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _write_json_payload(output_target: str, payload: dict) -> None:
    if output_target == "-":
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write('\n')
        return

    output_path = Path(output_target)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def _lineage_result_to_json_payload(file_name: str, assembler, result) -> dict:
    return {
        'file_name': file_name,
        'table_reads': sorted(getattr(result, 'table_reads', ())),
        'table_writes': sorted(getattr(result, 'table_writes', ())),
        'usage_reads': sorted(getattr(result, 'usage_reads', ())),
        'usage_writes': sorted(getattr(result, 'usage_writes', ())),
        'unresolved_dynamic_tables': sorted(getattr(result, 'unresolved_dynamic_tables', ())),
        'table_lineage_rows': assembler.to_table_lineage_rows(file_name, result),
    }


def _resolve_structured_output_target(
    output_path: str | None,
    default_prefix: str,
    output_format: str,
    stdin_mode: bool,
) -> str:
    if output_path:
        return output_path
    if stdin_mode:
        return '-'

    extension_map = {
        'csv': 'csv',
        'json': 'json',
    }
    return f'./output/{default_prefix}_{__import__("time").strftime("%Y%m%d%H%M%S")}.{extension_map[output_format]}'


def _table_usage_payload_from_result(file_name: str, assembler, result) -> dict:
    return {
        'file_name': file_name,
        'table_reads': sorted(getattr(result, 'table_reads', ())),
        'table_writes': sorted(getattr(result, 'table_writes', ())),
        'usage_reads': sorted(getattr(result, 'usage_reads', ())),
        'usage_writes': sorted(getattr(result, 'usage_writes', ())),
        'table_usage_rows': assembler.to_table_usage_rows(file_name, result),
    }


def _write_table_usage_output(output_target: str, output_format: str, payload: dict) -> None:
    if output_format == 'json':
        _write_json_payload(output_target, payload)
        return

    rows = payload['table_usage_rows']
    csv_rows = [
        [row['file_name'], row['access_type'], row['table_name']]
        for row in rows
    ]
    from .lineage.assembler import TABLE_USAGE_HEADERS
    _write_csv_rows(output_target, TABLE_USAGE_HEADERS, csv_rows)


def _write_table_lineage_output(output_target: str, output_format: str, payload: dict) -> None:
    if output_format == 'json':
        _write_json_payload(output_target, payload)
        return

    rows = payload['table_lineage_rows']
    csv_rows = [
        [
            row['file_name'],
            row['statement_index'],
            row['statement_type'],
            row['target_table'],
            row['source_table'],
            row['unresolved_dynamic_tables'],
        ]
        for row in rows
    ]
    from .lineage.assembler import TABLE_LINEAGE_HEADERS
    _write_csv_rows(output_target, TABLE_LINEAGE_HEADERS, csv_rows)


def cmd_extract(args):

    from .extraction.sql_extractor import SQLExtractor, ExtractorConfig

    config = ExtractorConfig(
        output_dir=args.output_dir,
        file_extension=args.file_ext,
        output_format=args.format,
    )
    extractor = SQLExtractor(config)
    success = extractor.process(args.path)
    return 0 if success else 1


def cmd_replace(args):

    import logging
    from .preprocessing.placeholder_replacer import PlaceholderReplacer
    from .utils.filename_generator import VersionedFileNameGenerator

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    constants_file = _resolve_cli_path(args.constants)

    if args.input_sql == '-':
        replacer = PlaceholderReplacer(
            str(constants_file),
            args.strict,
            args.recursive_import
        )
        try:
            new_content = replacer.replace_text(sys.stdin.read())
            if args.output and args.output != '-':
                output_sql_file = _resolve_cli_path(args.output)
                output_sql_file.parent.mkdir(parents=True, exist_ok=True)
                output_sql_file.write_text(new_content, encoding='utf-8')
            else:
                sys.stdout.write(new_content)
            return 0
        except Exception:
            logging.exception('Placeholder replacement failed.')
            return 1

    input_sql_file = _resolve_cli_path(args.input_sql)

    if args.output:
        output_sql_file = _resolve_cli_path(args.output)
    else:
        name_generator = VersionedFileNameGenerator()
        output_dir = Path.cwd() / 'output'
        output_sql_file = name_generator.generate(
            original_path=args.input_sql,
            output_dir=str(output_dir),
            prefix='PH'
        )

    replacer = PlaceholderReplacer(
        str(constants_file),
        args.strict,
        args.recursive_import
    )
    success = replacer.replace(str(input_sql_file), str(output_sql_file))
    return 0 if success else 1


def _build_cli_lineage_runtime(recursive):
    from .dependency.file_scanner import SQLFileDependencyScanner
    from .dependency.hive_sql_parser import HiveSQLDependencyExtractor, SQLConfig
    from .lineage.assembler import LineageAssembler
    from .lineage.backends.hive_native import HiveNativeLineageBackend
    from .lineage.service import LineageService

    processor = HiveSQLDependencyExtractor(SQLConfig())
    service = LineageService(HiveNativeLineageBackend(processor))
    assembler = LineageAssembler()
    scanner = SQLFileDependencyScanner(
        processor,
        recursive=recursive,
        service=service,
        assembler=assembler,
    )
    return scanner, service, assembler


def _write_cli_scan_csv(input_paths, output_file, recursive, headers, row_builder, row_serializer, log_message):
    scanner, service, assembler = _build_cli_lineage_runtime(recursive)
    sql_files = scanner.collect_sql_files(input_paths)
    if not sql_files:
        logging.warning('No SQL files found.')
        return

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open('w', newline='', encoding='utf-8') as output_handle:
        writer = csv.writer(output_handle)
        writer.writerow(headers)

        for sql_file in sorted(sql_files):
            result = service.parse_file(sql_file)
            rows = row_builder(assembler, sql_file.name, result)
            for row in rows:
                writer.writerow(row_serializer(row))

    logging.info(log_message, output_file)


def cmd_scan(args):

    output_format = args.format or ('json' if args.input == ['-'] else 'csv')

    if args.input == ['-']:
        _, service, assembler = _build_cli_lineage_runtime(recursive=False)
        result = service.parse_sql(sys.stdin.read())
        source_name = args.source_name or '<stdin>'
        payload = _table_usage_payload_from_result(source_name, assembler, result)
        output_target = _resolve_structured_output_target(args.output, 'table_usage', output_format, stdin_mode=True)
        _write_table_usage_output(output_target, output_format, payload)
        return 0

    scanner, service, assembler = _build_cli_lineage_runtime(args.recursive)
    sql_files = scanner.collect_sql_files(args.input)
    if not sql_files:
        logging.warning('No SQL files found.')
        return 0

    files_payload = []
    all_rows = []
    for sql_file in sorted(sql_files):
        result = service.parse_file(sql_file)
        payload = _table_usage_payload_from_result(sql_file.name, assembler, result)
        files_payload.append(payload)
        all_rows.extend(payload['table_usage_rows'])

    output_target = _resolve_structured_output_target(args.output, 'table_usage', output_format, stdin_mode=False)
    aggregate_payload = {
        'file_count': len(files_payload),
        'files': files_payload,
        'table_usage_rows': all_rows,
    }
    _write_table_usage_output(output_target, output_format, aggregate_payload)
    logging.info('Table usage has been written to: %s', output_target)
    return 0


def cmd_lineage(args):

    output_format = args.format or ('json' if args.input == ['-'] else 'csv')

    if args.input == ['-']:
        _, service, assembler = _build_cli_lineage_runtime(recursive=False)
        result = service.parse_sql(sys.stdin.read())
        source_name = args.source_name or '<stdin>'
        payload = _lineage_result_to_json_payload(source_name, assembler, result)
        output_target = _resolve_structured_output_target(args.output, 'table_lineage', output_format, stdin_mode=True)
        _write_table_lineage_output(output_target, output_format, payload)
        return 0

    scanner, service, assembler = _build_cli_lineage_runtime(args.recursive)
    sql_files = scanner.collect_sql_files(args.input)
    if not sql_files:
        logging.warning('No SQL files found.')
        return 0

    files_payload = []
    all_rows = []
    for sql_file in sorted(sql_files):
        result = service.parse_file(sql_file)
        payload = _lineage_result_to_json_payload(sql_file.name, assembler, result)
        files_payload.append(payload)
        all_rows.extend(payload['table_lineage_rows'])

    output_target = _resolve_structured_output_target(args.output, 'table_lineage', output_format, stdin_mode=False)
    aggregate_payload = {
        'file_count': len(files_payload),
        'files': files_payload,
        'table_lineage_rows': all_rows,
    }
    _write_table_lineage_output(output_target, output_format, aggregate_payload)
    logging.info('Table lineage has been written to: %s', output_target)
    return 0


def cmd_analyze(args):

    from .dependency.lineage_graph_analyzer import (
        CYCLE_HEADERS,
        detect_table_lineage_cycles,
        to_cycle_rows,
    )

    output_format = args.format or 'csv'
    cycles = detect_table_lineage_cycles(args.csv_file)
    rows = to_cycle_rows(cycles)
    output_target = _resolve_structured_output_target(args.output, 'table_lineage_cycles', output_format, stdin_mode=args.csv_file == '-')

    if output_format == 'json':
        _write_json_payload(
            output_target,
            {
                'cycle_count': len(cycles),
                'cycles': cycles,
                'cycle_rows': rows,
            },
        )
        return 0

    _write_csv_rows(
        output_target,
        CYCLE_HEADERS,
        [[row['cycle_id'], row['cycle_length'], row['sequence_index'], row['table_name']] for row in rows],
    )
    return 0


def cmd_lineage_graph(args):

    from .dependency.lineage_graph_analyzer import (
        detect_table_lineage_cycles,
        get_direct_downstream_tables,
        get_direct_upstream_tables,
    )

    if args.cycles:
        cycles = detect_table_lineage_cycles(args.csv_file)
        if not cycles:
            print('No table-level lineage cycles detected.')
            return 0

        for cycle in cycles:
            print(' -> '.join(cycle))
        return 0

    if args.upstream:
        upstream_tables = get_direct_upstream_tables(args.csv_file, args.upstream)
        if not upstream_tables:
            print(f'Table {args.upstream} has no direct upstream tables.')
            return 0

        for table_name in upstream_tables:
            print(table_name)
        return 0

    downstream_tables = get_direct_downstream_tables(args.csv_file, args.downstream)
    if not downstream_tables:
        print(f'Table {args.downstream} has no direct downstream tables.')
        return 0

    for table_name in downstream_tables:
        print(table_name)
    return 0


def build_parser():

    parser = argparse.ArgumentParser(
        description='SQL Asset Graph - unified command-line interface',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Available subcommands')

    p_extract = subparsers.add_parser(
        'extract-sql',
        aliases=['extract'],
        help='Extract SQL statements from Python files',
    )
    p_extract.add_argument('path', help='Python file or directory path')
    p_extract.add_argument('--output-dir', '-o', default='output', help='Output directory')
    p_extract.add_argument('--file-ext', default='.py', help='File extension to process')
    p_extract.add_argument('--format', choices=['sql', 'json', 'csv'], default='sql', help='Output format')
    p_extract.set_defaults(handler=cmd_extract)

    p_replace = subparsers.add_parser(
        'fill-placeholder',
        aliases=['replace'],
        help='Replace placeholders in SQL files',
    )
    p_replace.add_argument('input_sql', help='Input SQL file path')
    p_replace.add_argument('--output', '-o', help='Output SQL file path')
    p_replace.add_argument('--constants', '-c', required=True, help='Path to constants.py')
    p_replace.add_argument('--strict', '-s', action='store_true', help='Fail when a constant is missing')
    p_replace.add_argument('--no-recursive-import', action='store_false', dest='recursive_import',
                           help='Disable recursive import')
    p_replace.set_defaults(handler=cmd_replace)

    p_scan = subparsers.add_parser(
        'table-usage',
        aliases=['scan'],
        help='Scan SQL files and export table usage',
    )
    p_scan.add_argument('--input', '-i', nargs='+', required=True, help='Input SQL files or directories')
    p_scan.add_argument('--output', '-o', help='Output file path')
    p_scan.add_argument('--no-recursive', action='store_false', dest='recursive', help='Do not recurse into subdirectories')
    p_scan.add_argument('--format', choices=['csv', 'json'], help='Output format')
    p_scan.add_argument('--source-name', help='Synthetic file name used when reading SQL text from stdin')
    p_scan.set_defaults(handler=cmd_scan)

    p_lineage = subparsers.add_parser('lineage', help='Scan SQL files and export table lineage')
    p_lineage.add_argument('--input', '-i', nargs='+', required=True, help='Input SQL files or directories')
    p_lineage.add_argument('--output', '-o', help='Output lineage file path')
    p_lineage.add_argument('--no-recursive', action='store_false', dest='recursive', help='Do not recurse into subdirectories')
    p_lineage.add_argument('--format', choices=['csv', 'json'], help='Output format')
    p_lineage.add_argument('--source-name', help='Synthetic file name used when reading SQL text from stdin')
    p_lineage.set_defaults(handler=cmd_lineage)

    p_lineage_graph = subparsers.add_parser('lineage-graph', help='Query the table lineage graph')
    p_lineage_graph.add_argument('csv_file', help='Table lineage CSV file, or - to read from stdin')
    graph_query_group = p_lineage_graph.add_mutually_exclusive_group(required=True)
    graph_query_group.add_argument('--upstream', help='Show direct upstream tables for the target table')
    graph_query_group.add_argument('--downstream', help='Show direct downstream tables for the source table')
    graph_query_group.add_argument('--cycles', action='store_true', help='Detect table-level lineage cycles')
    p_lineage_graph.set_defaults(handler=cmd_lineage_graph)

    p_analyze = subparsers.add_parser(
        'lineage-cycles',
        aliases=['analyze'],
        help='Analyze table-level lineage cycles',
    )
    p_analyze.add_argument('csv_file', help='Table lineage CSV file, or - to read from stdin')
    p_analyze.add_argument('--output', '-o', help='Output cycle file path')
    p_analyze.add_argument('--format', choices=['csv', 'json'], default='csv', help='Output format')
    p_analyze.set_defaults(handler=cmd_analyze)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.handler(args)


if __name__ == '__main__':
    sys.exit(main())
