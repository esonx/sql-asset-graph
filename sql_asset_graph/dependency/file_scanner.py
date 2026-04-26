

import csv
from typing import Set, Tuple, List, Union, Dict
from dataclasses import dataclass
from pathlib import Path
import time
import logging
logging.basicConfig(level=logging.INFO)

from .hive_sql_parser import HiveSQLDependencyExtractor, SQLConfig
from sql_asset_graph.lineage.assembler import (
    LineageAssembler,
    TABLE_LINEAGE_HEADERS,
    TABLE_USAGE_HEADERS,
)
from sql_asset_graph.lineage.backends.hive_native import HiveNativeLineageBackend
from sql_asset_graph.lineage.service import LineageService

@dataclass
class SQLFileDependencyScanner:

    processor: HiveSQLDependencyExtractor
    recursive: bool = True
    service: LineageService | None = None
    assembler: LineageAssembler | None = None

    def __post_init__(self):
        if self.service is None:
            self.service = LineageService(HiveNativeLineageBackend(self.processor))
        if self.assembler is None:
            self.assembler = LineageAssembler()

    def get_sql_files(self, path: Union[str, Path]) -> Set[Path]:


        path = Path(path)
        if not path.exists():
            logging.warning(f"Path does not exist: {path}")
            return set()

        if path.is_file():
            return {path} if path.suffix.lower() == '.sql' else set()

        if path.is_dir():
            pattern = '**/*.sql' if self.recursive else '*.sql'
            return set(path.glob(pattern))

        return set()

    def process_single_file(self, sql_file: Path) -> Tuple[str, Set[str], Set[str]]:


        try:
            result = self.service.parse_file(sql_file)
            return sql_file.name, set(result.usage_reads), set(result.usage_writes)
        except Exception as e:
            logging.error(f"Error processing file {sql_file}: {str(e)}")
            return sql_file.name, set(), set()

    def process_single_file_usage_rows(self, sql_file: Path) -> Tuple[str, List[Dict[str, str]]]:
        try:
            result = self.service.parse_file(sql_file)
            return sql_file.name, self.assembler.to_table_usage_rows(sql_file.name, result)
        except Exception as e:
            logging.error(f"Error collecting table usage from {sql_file}: {str(e)}")
            return sql_file.name, []

    def process_single_file_lineage(self, sql_file: Path) -> Tuple[str, List[Dict[str, str]]]:

        try:
            result = self.service.parse_file(sql_file)
            return sql_file.name, self.assembler.to_table_lineage_rows(sql_file.name, result)
        except Exception as e:
            logging.error(f"Error collecting lineage from {sql_file}: {str(e)}")
            return sql_file.name, []

    def collect_sql_files(self, input_paths: Union[str, List[str], Path]) -> Set[Path]:


        sql_files = set()
        if isinstance(input_paths, (str, Path)):
            sql_files.update(self.get_sql_files(input_paths))
        elif isinstance(input_paths, list):
            for path in input_paths:
                sql_files.update(self.get_sql_files(path))
        else:
            raise ValueError("input_paths must be a string, Path, or a list of them")
        return sql_files

def process_sql_files(input_path: Union[str, List[str], Path],
                     output_file: str,
                     recursive: bool = True) -> None:


    try:

        config = SQLConfig()
        sql_processor = HiveSQLDependencyExtractor(config)
        file_processor = SQLFileDependencyScanner(sql_processor, recursive)


        sql_files = file_processor.collect_sql_files(input_path)
        if not sql_files:
            logging.warning("No SQL files found.")
            return


        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)


        with output_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(TABLE_USAGE_HEADERS)

            for sql_file in sorted(sql_files):
                logging.info(f"Processing: {sql_file}")
                _, rows = file_processor.process_single_file_usage_rows(sql_file)
                for row in rows:
                    writer.writerow([row['file_name'], row['access_type'], row['table_name']])

        logging.info(f"Table usage has been written to: {output_file}")

    except Exception as e:
        logging.error(f"Processing failed: {str(e)}")
        raise


def process_sql_lineage_files(input_path: Union[str, List[str], Path],
                              output_file: str,
                              recursive: bool = True) -> None:

    try:
        config = SQLConfig()
        sql_processor = HiveSQLDependencyExtractor(config)
        file_processor = SQLFileDependencyScanner(sql_processor, recursive)

        sql_files = file_processor.collect_sql_files(input_path)
        if not sql_files:
            logging.warning("No SQL files found.")
            return

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(TABLE_LINEAGE_HEADERS)

            for sql_file in sorted(sql_files):
                logging.info(f"Processing lineage: {sql_file}")
                _, rows = file_processor.process_single_file_lineage(sql_file)
                for row in rows:
                    writer.writerow([
                        row['file_name'],
                        row['statement_index'],
                        row['statement_type'],
                        row['target_table'],
                        row['source_table'],
                        row['unresolved_dynamic_tables'],
                    ])

        logging.info(f"Table lineage has been written to: {output_file}")

    except Exception as e:
        logging.error(f"Lineage processing failed: {str(e)}")
        raise

def main():

    import argparse

    parser = argparse.ArgumentParser(description='SQL table dependency scanner')
    parser.add_argument('--input', '-i',
                       nargs='+',
                       help='Input SQL file or directory path',
                       required=True)
    parser.add_argument('--output', '-o',
                       help='Output CSV file path',
                       default=f'./output/table_usage_{time.strftime("%Y%m%d%H%M%S")}.csv')
    parser.add_argument('--no-recursive',
                       action='store_false',
                       dest='recursive',
                       help='Do not recurse into subdirectories')

    args = parser.parse_args()
    process_sql_files(args.input, args.output, args.recursive)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
