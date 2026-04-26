# SQL Asset Graph

SQL Asset Graph is a command-line tool optimized for HiveSQL and SparkSQL asset analysis, covering SQL extraction, table usage scanning, table-level lineage generation, lineage cycle analysis, and graph-style lineage queries.

The current release is deliberately tuned for HiveSQL and SparkSQL-style warehouse scripts rather than broad multi-dialect parsing. In repository-scale Hive/Spark SQL projects with dynamic table templates, embedded SQL, and stable CSV output contracts, it provides stronger practical detection coverage than generic open-source lineage tools that primarily target isolated statements or broad ANSI-style dialect support.

It is designed for repository-style SQL assets instead of isolated ad hoc statements, and it supports extracting embedded SQL from Python files, replacing placeholders before analysis, exporting stable CSV outputs, and querying upstream or downstream table relationships from generated lineage data.

## Quick Start

Install from the current repository:

```bash
pip install -e .
```

After installation, you can use either entrypoint:

```bash
python -m sql_asset_graph.main --help
sql-asset-graph --help
```

Generate table usage information from a directory of SQL files:

```bash
sql-asset-graph table-usage -i ./sql_dir -o ./output/table_usage.csv
```

Expected CSV header:

```text
file_name,access_type,table_name
```

Generate direct table lineage:

```bash
sql-asset-graph lineage -i ./sql_dir -o ./output/table_lineage.csv
```

Expected CSV header:

```text
file_name,statement_index,statement_type,target_table,source_table,unresolved_dynamic_tables
```

Analyze table-level lineage cycles from lineage output:

```bash
sql-asset-graph lineage-cycles ./output/table_lineage.csv
```

Cycle CSV header:

```text
cycle_id,cycle_length,sequence_index,table_name
```

For lightweight shell usage, `lineage-cycles` also accepts `-` as the input path and reads `table_lineage.csv` content from stdin. Legacy alias: `analyze`.

## Current Focus

SQL Asset Graph currently works best for HiveSQL and SparkSQL-style batch SQL workflows, especially when SQL lives in repositories together with Python orchestration scripts.

- Focused on Hive-style DML and lineage paths such as `INSERT OVERWRITE`, `CREATE TABLE AS SELECT`, and `CREATE VIEW AS SELECT`
- Optimized for repository-scale SQL processing instead of one-off interactive parsing
- Suitable when SQL is extracted from Python first and then passed through placeholder replacement, table usage export, lineage, and lineage cycle analysis

## Current Advantages

Compared with generic SQL lineage tooling, the current version is strongest in HiveSQL and SparkSQL repository workflows.

1. HiveSQL and SparkSQL-style workflow focus.
2. Stable CSV outputs for downstream automation.
3. Conservative handling of dynamic table templates.
4. End-to-end repository workflow from extraction to lineage query.
5. A default native Hive-oriented backend rather than a thin wrapper over a generic parser.

In practical terms, that means the current version is a better fit when you care more about predictable detection for HiveSQL/SparkSQL warehouse scripts than about supporting every SQL dialect equally.

## What It Does

SQL Asset Graph provides an end-to-end workflow for repository-based SQL analysis.

1. Extract SQL fragments from Python files.
2. Replace placeholder variables in SQL files.
3. Scan SQL files to identify read and write table usage.
4. Generate direct table-level lineage rows.
5. Analyze table-level lineage cycles.
6. Query upstream, downstream, and cyclic relationships from lineage CSV output.

The current implementation is intentionally specialized: it favors HiveSQL and SparkSQL-style repository assets, stable output contracts, and conservative lineage behavior over broad multi-engine dialect coverage.

## Typical Use Cases

SQL Asset Graph is a good fit when you need one or more of the following:

1. Batch analysis of SQL files stored in a repository.
2. Preprocessing SQL that is embedded in Python scripts.
3. Stable CSV outputs that can be consumed by downstream tools.
4. Table-level lineage for HiveSQL or SparkSQL-style SQL workflows.
5. Lightweight lineage graph queries without introducing a separate service.

## Command Overview

The CLI exposes six main commands.

### extract-sql

Extract SQL strings from Python files or directories.

```bash
python -m sql_asset_graph.main extract-sql /path/to/file.py
python -m sql_asset_graph.main extract-sql /path/to/python_dir -o ./output
python -m sql_asset_graph.main extract-sql /path/to/file.py --format json
python -m sql_asset_graph.main extract-sql /path/to/file.py --format csv
```

Legacy alias: `extract`

### fill-placeholder

Replace placeholders in SQL files using values from a constants module.

```bash
python -m sql_asset_graph.main fill-placeholder input.sql -c path/to/constants.py
python -m sql_asset_graph.main fill-placeholder input.sql -c path/to/constants.py -s
cat input.sql | python -m sql_asset_graph.main fill-placeholder - -c path/to/constants.py
```

Legacy alias: `replace`

### table-usage

Scan SQL files and export table read/write usage.

```bash
python -m sql_asset_graph.main table-usage -i ./sample.sql
python -m sql_asset_graph.main table-usage -i ./sql_dir -o ./output/table_usage.csv
python -m sql_asset_graph.main table-usage -i ./sql_dir --format json -o ./output/table_usage.json
cat sample.sql | python -m sql_asset_graph.main table-usage -i - --source-name sample.sql
cat sample.sql | python -m sql_asset_graph.main table-usage -i - --format csv --source-name sample.sql
```

Legacy alias: `scan`

Output header:

```text
file_name,access_type,table_name
```

### lineage

Generate direct table-level lineage.

```bash
python -m sql_asset_graph.main lineage -i ./sample.sql
python -m sql_asset_graph.main lineage -i ./sql_dir -o ./output/table_lineage.csv
python -m sql_asset_graph.main lineage -i ./sql_dir --format json -o ./output/table_lineage.json
cat sample.sql | python -m sql_asset_graph.main lineage -i - --source-name sample.sql
cat sample.sql | python -m sql_asset_graph.main lineage -i - --format csv --source-name sample.sql
```

Output header:

```text
file_name,statement_index,statement_type,target_table,source_table,unresolved_dynamic_tables
```

### lineage-graph

Query lineage relationships from generated CSV output.

```bash
python -m sql_asset_graph.main lineage-graph output/table_lineage.csv --upstream APP.TARGET_Y
python -m sql_asset_graph.main lineage-graph output/table_lineage.csv --downstream APP.SOURCE_X
python -m sql_asset_graph.main lineage-graph output/table_lineage.csv --cycles
cat output/table_lineage.csv | python -m sql_asset_graph.main lineage-graph - --upstream APP.TARGET_Y
```

### lineage-cycles

Analyze table-level lineage cycles from `table_lineage.csv`.

```bash
python -m sql_asset_graph.main lineage-cycles output/table_lineage.csv
python -m sql_asset_graph.main lineage-cycles output/table_lineage.csv --format json -o cycles.json
cat output/table_lineage.csv | python -m sql_asset_graph.main lineage-cycles -
```

Legacy alias: `analyze`

Cycle CSV header:

```text
cycle_id,cycle_length,sequence_index,table_name
```

## Output Files

The tool produces plain files that are easy to inspect or integrate into other workflows.

- `*_extracted_sql_*.sql`: extracted SQL collected from Python sources
- `*_extracted_sql_*.json`: structured extracted SQL records
- `*_extracted_sql_*.csv`: tabular extracted SQL records
- `table_usage_*.csv`: table read/write usage rows with header `file_name,access_type,table_name`
- `table_usage_*.json`: structured table read/write usage payload
- `table_lineage_*.csv`: direct table lineage rows with header `file_name,statement_index,statement_type,target_table,source_table,unresolved_dynamic_tables`
- `table_lineage_*.json`: structured table lineage payload
- `table_lineage_cycles_*.csv`: detected table-level lineage cycles with header `cycle_id,cycle_length,sequence_index,table_name`
- `table_lineage_cycles_*.json`: structured table-level lineage cycle payload

## Current Scope

SQL Asset Graph currently focuses on table-level lineage.

- It does not provide column-level lineage.
- It is optimized for HiveSQL and SparkSQL-style repository processing rather than broad multi-dialect SQL coverage.
- It is especially suitable when you need both CSV/JSON exports and follow-up lineage analysis.
- Dynamic table templates are treated conservatively and may be reported separately instead of being forced into guessed lineage edges.

## Requirements

- Python 3.9+
- Standard library only

## License

See [LICENSE](LICENSE).
