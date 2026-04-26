# SQL Asset Graph

[![PyPI version](https://img.shields.io/pypi/v/sql-asset-graph.svg)](https://pypi.org/project/sql-asset-graph/)
[![Python versions](https://img.shields.io/pypi/pyversions/sql-asset-graph.svg)](https://pypi.org/project/sql-asset-graph/)
[![License](https://img.shields.io/pypi/l/sql-asset-graph.svg)](https://pypi.org/project/sql-asset-graph/)

SQL Asset Graph is a command-line tool for repository-scale SQL analysis, optimized for HiveSQL and SparkSQL workflows. It focuses on extracting embedded SQL, exporting table usage, generating direct table lineage, detecting lineage cycles, and querying lineage graphs from stable CSV or JSON outputs.

It is deliberately specialized for warehouse-style SQL repositories rather than broad multi-dialect parsing. In HiveSQL and SparkSQL projects with embedded SQL, dynamic table templates, and batch-style lineage workflows, it is designed to provide a more predictable operational result than generic statement-oriented lineage tools.

## Quick Start

Install from PyPI:

```bash
pip install sql-asset-graph
```

For local development, you can still install from the current repository:

```bash
pip install -e .
```

After installation:

```bash
sql-asset-graph --help
python -m sql_asset_graph.main --help
```

Generate table usage from SQL files:

```bash
sql-asset-graph table-usage -i ./sql_dir -o ./output/table_usage.csv
```

Generate direct table lineage:

```bash
sql-asset-graph lineage -i ./sql_dir -o ./output/table_lineage.csv
```

Analyze table-level lineage cycles:

```bash
sql-asset-graph lineage-cycles ./output/table_lineage.csv
```

## What It Does

SQL Asset Graph provides an end-to-end workflow for repository-based SQL analysis.

1. Extract SQL fragments from Python files.
2. Replace placeholder variables in SQL files.
3. Export table read and write usage.
4. Generate direct table-level lineage rows.
5. Analyze table-level lineage cycles.
6. Query upstream, downstream, and cyclic relationships from lineage outputs.

## Command Overview

### `extract-sql`

Extract SQL strings from Python files or directories.

```bash
sql-asset-graph extract-sql /path/to/file.py
sql-asset-graph extract-sql /path/to/python_dir -o ./output
sql-asset-graph extract-sql /path/to/file.py --format json
sql-asset-graph extract-sql /path/to/file.py --format csv
```

Legacy alias: `extract`

### `fill-placeholder`

Replace placeholders in SQL files using values from a constants module.

```bash
sql-asset-graph fill-placeholder input.sql -c path/to/constants.py
sql-asset-graph fill-placeholder input.sql -c path/to/constants.py -s
cat input.sql | sql-asset-graph fill-placeholder - -c path/to/constants.py
```

Legacy alias: `replace`

### `table-usage`

Export table read and write usage from SQL files.

```bash
sql-asset-graph table-usage -i ./sample.sql
sql-asset-graph table-usage -i ./sql_dir -o ./output/table_usage.csv
sql-asset-graph table-usage -i ./sql_dir --format json -o ./output/table_usage.json
cat sample.sql | sql-asset-graph table-usage -i - --source-name sample.sql
cat sample.sql | sql-asset-graph table-usage -i - --format csv --source-name sample.sql
```

Legacy alias: `scan`

CSV header:

```text
file_name,access_type,table_name
```

### `lineage`

Generate direct table-level lineage from SQL files.

```bash
sql-asset-graph lineage -i ./sample.sql
sql-asset-graph lineage -i ./sql_dir -o ./output/table_lineage.csv
sql-asset-graph lineage -i ./sql_dir --format json -o ./output/table_lineage.json
cat sample.sql | sql-asset-graph lineage -i - --source-name sample.sql
cat sample.sql | sql-asset-graph lineage -i - --format csv --source-name sample.sql
```

CSV header:

```text
file_name,statement_index,statement_type,target_table,source_table,unresolved_dynamic_tables
```

### `lineage-cycles`

Analyze table-level lineage cycles from `table_lineage.csv`.

```bash
sql-asset-graph lineage-cycles output/table_lineage.csv
sql-asset-graph lineage-cycles output/table_lineage.csv --format json -o cycles.json
cat output/table_lineage.csv | sql-asset-graph lineage-cycles -
```

Legacy alias: `analyze`

CSV header:

```text
cycle_id,cycle_length,sequence_index,table_name
```

### `lineage-graph`

Query upstream, downstream, and cycle relationships from lineage outputs.

```bash
sql-asset-graph lineage-graph output/table_lineage.csv --upstream APP.TARGET_Y
sql-asset-graph lineage-graph output/table_lineage.csv --downstream APP.SOURCE_X
sql-asset-graph lineage-graph output/table_lineage.csv --cycles
cat output/table_lineage.csv | sql-asset-graph lineage-graph - --upstream APP.TARGET_Y
```

## Typical Workflow

For repository-style SQL projects, the common workflow is:

```bash
sql-asset-graph extract-sql ./python_jobs -o ./output
sql-asset-graph fill-placeholder ./output/jobs_extracted_sql_*.sql -c ./constants.py -o ./output/jobs_filled.sql
sql-asset-graph table-usage -i ./output/jobs_filled.sql -o ./output/table_usage.csv
sql-asset-graph lineage -i ./output/jobs_filled.sql -o ./output/table_lineage.csv
sql-asset-graph lineage-cycles ./output/table_lineage.csv
```

If you already have SQL files, you can skip extraction and placeholder replacement.

## Output Files

- `*_extracted_sql_*.sql`: extracted SQL collected from Python sources
- `*_extracted_sql_*.json`: structured extracted SQL records
- `*_extracted_sql_*.csv`: tabular extracted SQL records
- `table_usage_*.csv`: table read/write usage rows
- `table_usage_*.json`: structured table usage payload
- `table_lineage_*.csv`: direct table lineage rows
- `table_lineage_*.json`: structured table lineage payload
- `table_lineage_cycles_*.csv`: detected table-level lineage cycles
- `table_lineage_cycles_*.json`: structured lineage cycle payload

## Current Focus

SQL Asset Graph currently works best for HiveSQL and SparkSQL-style batch SQL workflows, especially when SQL lives in repositories together with Python orchestration scripts.

- Focused on Hive-style DML and lineage paths such as `INSERT OVERWRITE`, `CREATE TABLE AS SELECT`, and `CREATE VIEW AS SELECT`
- Optimized for repository-scale SQL processing instead of one-off interactive parsing
- Suitable when SQL is extracted from Python first and then passed through placeholder replacement, table usage export, lineage, and lineage cycle analysis

## Current Scope

- Table-level lineage only; no column-level lineage
- Optimized for HiveSQL and SparkSQL-oriented repository processing rather than broad multi-dialect SQL coverage
- Dynamic table templates are handled conservatively and may be reported separately instead of being forced into guessed lineage edges
- Stable CSV and JSON outputs are prioritized for downstream automation

## Requirements

- Python 3.9+
- Standard library only

## License

See [LICENSE](LICENSE).
