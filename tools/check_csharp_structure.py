#!/usr/bin/env python3
"""Limited lexical/delimiter check, deliberately NOT a C# parser or compiler."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check(path):
    source = path.read_text(encoding="utf-8-sig")
    length = len(source)
    delimiters = []

    def fail(message, offset):
        raise AssertionError(f"{path.relative_to(ROOT)}:{source.count(chr(10), 0, offset) + 1}: {message}")

    def quoted(offset, quote, verbatim=False, interpolated=False):
        i = offset
        while i < length:
            char = source[i]
            if char == quote:
                if verbatim and i + 1 < length and source[i + 1] == quote:
                    i += 2
                    continue
                return i + 1
            if char == "\\" and not verbatim:
                i += 2
                continue
            if char == "\n" and not verbatim:
                fail("newline in a non-verbatim literal", i)
            if interpolated and char == "{":
                if i + 1 < length and source[i + 1] == "{":
                    i += 2
                else:
                    i = code(i + 1, interpolation=True)
                continue
            if interpolated and char == "}" and i + 1 < length and source[i + 1] == "}":
                i += 2
                continue
            i += 1
        fail("unterminated string/character literal", offset)

    def code(offset=0, interpolation=False):
        i = offset
        nested = 0
        while i < length:
            char = source[i]
            if source.startswith("//", i):
                end = source.find("\n", i)
                i = length if end < 0 else end + 1
                continue
            if source.startswith("/*", i):
                end = source.find("*/", i + 2)
                if end < 0:
                    fail("unterminated comment", i)
                i = end + 2
                continue
            raw = re.match(r'\$*("{3,})', source[i:]) if char in '$"' else None
            if raw:
                quote = raw.group(1)
                end = source.find(quote, i + len(raw.group(0)))
                if end < 0:
                    fail("unterminated raw string", i)
                i = end + len(quote)
                continue
            prefix = re.match(r'(\$@|@\$|\$|@)?"', source[i:]) if char in '$@"' else None
            if prefix:
                token = prefix.group(0)
                i = quoted(i + len(token), '"', '@' in token, '$' in token)
                continue
            if char == "'":
                i = quoted(i + 1, "'")
                continue
            if interpolation and char == "}" and nested == 0:
                return i + 1
            if char in "{([":
                delimiters.append((char, i))
                if interpolation and char == "{":
                    nested += 1
            elif char in "})]":
                if not delimiters or delimiters[-1][0] != {"}": "{", ")": "(", "]": "["}[char]:
                    fail("unmatched delimiter " + char, i)
                delimiters.pop()
                if interpolation and char == "}":
                    nested -= 1
            i += 1
        if interpolation:
            fail("unterminated interpolation", offset)
        return i

    code()
    if delimiters:
        fail("unclosed delimiter " + delimiters[-1][0], delimiters[-1][1])


def main():
    files = [p for p in ROOT.rglob('*.cs') if not {'obj', 'bin'}.intersection(p.parts)]
    for path in files:
        check(path)
    print(f"Limited C# structural check: {len(files)} files; not grammar/type checking or compilation")


if __name__ == '__main__':
    main()
