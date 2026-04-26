

import re
import os
import sys
import logging
import argparse
import importlib.util
import ast
from typing import Optional, Dict, Any

from ..utils.filename_generator import VersionedFileNameGenerator


def _resolve_cli_path(path_str: str) -> str:
    path = os.path.expanduser(path_str)
    if os.path.isabs(path):
        return path
    return os.path.abspath(path)


class PlaceholderReplacer:


    def __init__(self, constants_path: str, strict: bool = False, recursive_import: bool = True):


        self.strict = strict
        self.recursive_import = recursive_import
        self._constants_module = None
        self._constants_cache: Dict[str, Any] = {}
        self._placeholder_pattern = re.compile(r'\{constants\.([a-zA-Z][a-zA-Z0-9_]*)\}')
        self._load_constants(constants_path)

    def _load_constants(self, constants_path: str) -> None:


        if not os.path.exists(constants_path):
            raise ImportError(f"Constants file not found at {constants_path}")

        try:
            if self.recursive_import:
                self._load_module_recursive(constants_path)
            else:
                self._load_module_safe(constants_path)
            logging.info(f"Successfully loaded constants from {constants_path}")
        except Exception as e:
            raise ImportError(f"Failed to load constants: {str(e)}")

    def _load_module_safe(self, path: str) -> None:

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content)


        safe_context = {}


        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    try:

                        value_code = compile(ast.Expression(node.value), '<string>', 'eval')
                        safe_context[target.id] = eval(value_code, {"__builtins__": {}}, safe_context)
                    except Exception:

                        pass


        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id not in safe_context:
                    try:
                        value_code = compile(ast.Expression(node.value), '<string>', 'eval')
                        safe_context[target.id] = eval(value_code, {"__builtins__": {}}, safe_context)
                    except Exception:
                        pass


        for name, value in safe_context.items():
            if not name.startswith('_') and name not in self._constants_cache:
                self._constants_cache[name] = value

    def _load_module_recursive(self, path: str, visited: Optional[set] = None) -> None:

        if visited is None:
            visited = set()

        abs_path = os.path.abspath(path)
        if abs_path in visited:
            return
        visited.add(abs_path)

        module_name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            raise ImportError(f"Could not create spec from {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)


        for name in dir(module):
            if name.isupper() and name not in self._constants_cache:
                self._constants_cache[name] = getattr(module, name)


        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        import_matches = re.findall(r'^\s*from\s+(\.?)(\w+)\s+import\s+', content, re.MULTILINE)

        for dot, module_name in import_matches:
            try:
                base_dir = os.path.dirname(path)
                if dot:
                    imported_path = os.path.join(base_dir, f"{module_name}.py")
                else:
                    imported_path = os.path.join(base_dir, f"{module_name}.py")

                if os.path.exists(imported_path):
                    self._load_module_recursive(imported_path, visited)
            except Exception as e:
                logging.warning(f"Could not recursively load {module_name}: {e}")

    def _get_constant(self, name: str) -> Optional[str]:


        return str(self._constants_cache.get(name)) if name in self._constants_cache else None

    def replace_text(self, sql_content: str) -> str:


        def replace_match(match):
            placeholder_name = match.group(1)
            value = self._get_constant(placeholder_name)

            if value is not None:
                return value

            if self.strict:
                raise KeyError(f"Constant '{placeholder_name}' not found")

            logging.warning(
                f"Constant '{placeholder_name}' not found, keeping original placeholder"
            )
            return match.group(0)

        return self._placeholder_pattern.sub(replace_match, sql_content)

    def replace(self, input_path: str, output_path: str) -> bool:


        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
        except FileNotFoundError:
            logging.error(f"Input file not found: {input_path}")
            raise

        try:
            new_content = self.replace_text(sql_content)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            logging.info(f"Successfully replaced placeholders and saved to {output_path}")
            return True

        except IOError as e:
            logging.error(f"Failed to write output file: {e}")
            raise
        except Exception as e:
            logging.error(f"Error during replacement: {e}")
            return False


def main():


    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )

    parser = argparse.ArgumentParser(
        description='Replace placeholders in SQL files with constant values.'
    )
    parser.add_argument('input_sql', help='Input SQL file path')
    parser.add_argument(
        '--output', '-o',
        help='Output SQL file path. If not provided, will generate timestamped name.'
    )
    parser.add_argument(
        '--constants', '-c',
        required=True,
        help='Path to constants.py file'
    )
    parser.add_argument(
        '--strict', '-s',
        action='store_true',
        help='Raise error if constant not found'
    )
    parser.add_argument(
        '--no-recursive-import',
        action='store_false',
        dest='recursive_import',
        help='Disable recursive import of constants'
    )

    args = parser.parse_args()

    input_sql_file = _resolve_cli_path(args.input_sql)
    constants_file = _resolve_cli_path(args.constants)


    if args.output:
        user_output_path = _resolve_cli_path(args.output)

        if os.path.isdir(user_output_path) or (not os.path.exists(user_output_path) and not '.' in os.path.basename(user_output_path)):

            name_generator = VersionedFileNameGenerator()
            output_sql_file = name_generator.generate(
                original_path=args.input_sql,
                output_dir=user_output_path,
                prefix='PH'
            )
        else:

            output_sql_file = user_output_path
    else:

        name_generator = VersionedFileNameGenerator()
        output_dir = os.path.abspath('output')
        output_sql_file = name_generator.generate(
            original_path=args.input_sql,
            output_dir=output_dir,
            prefix='PH'
        )

    try:
        replacer = PlaceholderReplacer(
            constants_file,
            args.strict,
            args.recursive_import
        )
        success = replacer.replace(input_sql_file, output_sql_file)
        return 0 if success else 1
    except (ImportError, FileNotFoundError, IOError) as e:
        logging.error(str(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
