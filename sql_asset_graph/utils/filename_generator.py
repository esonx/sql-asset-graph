

import os
import re
from typing import Optional, List, Tuple

class VersionedFileNameGenerator:


    @staticmethod
    def _split_camel_case(text: str) -> List[str]:


        if text and text[0].isupper():
            text = text[0].lower() + text[1:]


        words = re.finditer(r'.+?(?:(?<=[a-z])(?=[A-Z])|$)', text)
        return [m.group(0) for m in words]

    @staticmethod
    def _split_by_separator(text: str, separator: str) -> List[str]:


        return [word for word in text.split(separator) if word]

    @staticmethod
    def _split_snake_case(text: str) -> List[str]:


        words = [word for word in text.split('_') if word]

        if all(word.isupper() for word in words):
            return [word.lower() for word in words]
        return words

    @staticmethod
    def _detect_format(text: str) -> List[str]:


        formats = []


        if '_' in text:
            if text.isupper():
                formats.append('upper_snake')
            elif any(c.isupper() for c in text.split('_')[0]):
                formats.append('mixed_snake')
            formats.append('snake')

        if '-' in text:
            formats.append('kebab')

        if '.' in text and not text.startswith('.') and not text.endswith('.'):
            formats.append('dot')


        parts = re.split(r'[_\-.]', text)
        for part in parts:
            if part and part[0].isupper() and not part.isupper():
                if re.match(r'^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)*$', part):
                    formats.append('pascal')
            elif re.match(r'^[a-z][a-z0-9]*(?:[A-Z][a-z0-9]*)*$', part):
                formats.append('camel')

        return formats or ['unknown']

    def _abbreviate_name(self, filename: str) -> Tuple[str, str]:


        suffix_match = re.search(r'_(\d{8,})$', filename)
        if suffix_match:
            numeric_part = suffix_match.group(1)
            name_part = filename[:suffix_match.start()]
        else:
            numeric_part = ""
            name_part = filename


        parts = [p for p in re.split(r'[_\-.]', name_part) if p and not p.isdigit()]
        words = []


        for part in parts:

            formats = self._detect_format(part)


            if 'pascal' in formats or 'camel' in formats:
                words.extend(self._split_camel_case(part))
            elif part.isupper() and len(part) > 1:

                words.append(part.lower())
            else:
                words.append(part.lower())


        seen = set()
        unique_words = []
        for word in words:
            if word not in seen:
                seen.add(word)
                unique_words.append(word)


        abbrev = ''.join(word[0].upper() for word in unique_words if word and word[0].isalpha())

        return abbrev, numeric_part

    def generate(
        self,
        original_path: str,
        output_dir: str,
        prefix: str,
        start_version: int = 1,
        use_abbreviation: bool = False
    ) -> str:


        if not prefix:
            raise ValueError("前缀不能为空。")

        prefix_upper = prefix.upper()
        original_filename = os.path.basename(original_path)
        name, ext = os.path.splitext(original_filename)
        version = start_version

        if use_abbreviation:

            abbrev, numeric_suffix = self._abbreviate_name(name)

            if numeric_suffix:

                abbreviated_name = f"{abbrev}_{numeric_suffix}"
            else:
                abbreviated_name = abbrev
            name = abbreviated_name

        while True:
            new_filename = f"{prefix_upper}v{version}_{name}{ext}"
            new_filepath = os.path.join(output_dir, new_filename)

            if not os.path.exists(new_filepath):
                return new_filepath

            version += 1

