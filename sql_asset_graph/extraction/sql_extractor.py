

import re
import os
import logging
import argparse
import csv
import json
from datetime import datetime
from typing import List, Optional, Pattern
from dataclasses import dataclass

@dataclass
class ExtractorConfig:


    sql_pattern: str = r'\w+\s*=\s*f?("""(.*?)"""|\'\'\'(.*?)\'\'\')'
    output_dir: str = 'output'
    file_extension: str = '.py'
    output_format: str = 'sql'


class SQLExtractor:


    def __init__(self, config: Optional[ExtractorConfig] = None):


        self.config = config or ExtractorConfig()
        self._sql_pattern: Pattern = re.compile(self.config.sql_pattern, re.DOTALL)
        self._setup_logging()

    def _setup_logging(self) -> None:

        logging.basicConfig(
            level=logging.INFO,
            format='%(levelname)s: %(message)s'
        )

    def _extract_from_file(self, file_path: str) -> List[str]:


        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (FileNotFoundError, IOError) as e:
            logging.error(f"Could not read file {file_path}: {e}")
            raise

        sql_matches = self._sql_pattern.findall(content)
        if not sql_matches:
            return []

        queries = []
        for match in sql_matches:
            sql = match[1] if match[1] else match[2]
            if sql.strip():
                queries.append(sql.strip())
        return queries

    def _build_query_records(self, file_queries: List[tuple[str, str, List[str]]]) -> List[dict]:

        records = []
        for file_path, source_path, queries in file_queries:
            file_name = os.path.basename(file_path)
            for index, sql_text in enumerate(queries, 1):
                records.append({
                    'file_name': file_name,
                    'source_path': source_path,
                    'query_index': str(index),
                    'sql_text': sql_text,
                })
        return records

    def _write_queries(self,
                      output_path: str,
                      file_queries: List[tuple[str, str, List[str]]]) -> int:


        total_queries = 0
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f_out:
                for file_path, source_path, queries in file_queries:
                    if not queries:
                        continue
                    f_out.write(f"-- {'#' * 54}\n")
                    f_out.write(f"-- Start of SQL from: {source_path}\n")
                    f_out.write(f"-- {'#' * 54}\n\n")

                    for i, sql in enumerate(queries, 1):
                        f_out.write(f"-- Query {i} from {os.path.basename(file_path)}\n")
                        f_out.write(sql)
                        f_out.write("\n\n-- End of Query\n\n")

                    total_queries += len(queries)
                    f_out.write(f"-- {'#' * 54}\n")
                    f_out.write(f"-- End of SQL from: {source_path}\n")
                    f_out.write(f"-- {'#' * 54}\n\n\n")

            return total_queries

        except IOError as e:
            logging.error(f"Failed to write output file: {e}")
            raise

    def _write_queries_json(self, output_path: str, query_records: List[dict]) -> int:

        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            payload = {
                'query_count': len(query_records),
                'queries': query_records,
            }
            with open(output_path, 'w', encoding='utf-8') as output_handle:
                json.dump(payload, output_handle, ensure_ascii=False, indent=2)
                output_handle.write('\n')
            return len(query_records)
        except IOError as e:
            logging.error(f"Failed to write output file: {e}")
            raise

    def _write_queries_csv(self, output_path: str, query_records: List[dict]) -> int:

        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', newline='', encoding='utf-8') as output_handle:
                writer = csv.DictWriter(
                    output_handle,
                    fieldnames=['file_name', 'source_path', 'query_index', 'sql_text'],
                )
                writer.writeheader()
                writer.writerows(query_records)
            return len(query_records)
        except IOError as e:
            logging.error(f"Failed to write output file: {e}")
            raise

    def _get_output_extension(self) -> str:
        extension_map = {
            'sql': '.sql',
            'json': '.json',
            'csv': '.csv',
        }
        return extension_map[self.config.output_format]

    def _write_output(self, output_path: str, file_queries: List[tuple[str, str, List[str]]]) -> int:
        if self.config.output_format == 'sql':
            return self._write_queries(output_path, file_queries)

        query_records = self._build_query_records(file_queries)
        if self.config.output_format == 'json':
            return self._write_queries_json(output_path, query_records)
        if self.config.output_format == 'csv':
            return self._write_queries_csv(output_path, query_records)
        raise ValueError(f"Unsupported output format: {self.config.output_format}")

    def process(self, path: str) -> bool:


        try:

            files_to_process = []
            if os.path.isfile(path) and path.endswith(self.config.file_extension):
                files_to_process.append(path)
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        if file.endswith(self.config.file_extension):
                            files_to_process.append(os.path.join(root, file))
            else:
                logging.error(f"Invalid path: {path}")
                return False

            if not files_to_process:
                logging.warning("No Python files found to process.")
                return False

            files_to_process.sort()


            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            base_name = os.path.splitext(os.path.basename(path))[0]
            source_root = os.path.dirname(path.rstrip(os.sep)) or '.'
            output_path = os.path.join(
                self.config.output_dir,
                f"{base_name}_extracted_sql_{timestamp}{self._get_output_extension()}"
            )


            file_queries = [
                (
                    f,
                    os.path.relpath(f, start=source_root),
                    self._extract_from_file(f),
                )
                for f in files_to_process
            ]


            total_queries = self._write_output(output_path, file_queries)

            if total_queries > 0:
                logging.info(f"Successfully extracted {total_queries} SQL queries to {output_path}")
                return True
            else:
                logging.info("No SQL queries found in the specified path.")
                if os.path.exists(output_path):
                    os.remove(output_path)
                return False

        except Exception as e:
            logging.error(f"Processing failed: {str(e)}")
            return False


def main():

    parser = argparse.ArgumentParser(
        description='Extract SQL statements from Python files.'
    )
    parser.add_argument(
        'path',
        help='Python file or directory to process'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='output',
        help='Output directory for SQL files'
    )
    parser.add_argument(
        '--file-ext',
        default='.py',
        help='File extension to process'
    )
    parser.add_argument(
        '--format',
        choices=['sql', 'json', 'csv'],
        default='sql',
        help='Output format'
    )

    args = parser.parse_args()

    config = ExtractorConfig(
        output_dir=args.output_dir,
        file_extension=args.file_ext,
        output_format=args.format,
    )

    extractor = SQLExtractor(config)
    success = extractor.process(args.path)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
