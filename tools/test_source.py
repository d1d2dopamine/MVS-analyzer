#!/usr/bin/env python3
"""Offline regressions for documentation checks; no C# execution."""
from pathlib import Path
import tempfile
import unittest
from check_source import check_readme, ROOT


class SourceTests(unittest.TestCase):
    def test_actual_public_readme(self):
        check_readme(ROOT)

    def test_badge_versions_and_attribute_order_are_editable(self):
        with tempfile.TemporaryDirectory() as d:
            for html in ['<img src="https://img.shields.io/badge/app-1.4.0-blue" alt="app">',
                         "<IMG alt='updated label'\r\n width='100' src='https://img.shields.io/badge/app-2.0.0-blue' />",
                         'A README without badges is valid too.']:
                check_readme(d, html)

    def test_local_image_remains_checked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'logo.png').write_bytes(b'fixture')
            check_readme(root, '<img alt="Logo" src="logo.png">')
            with self.assertRaisesRegex(AssertionError, 'Missing or unsafe'):
                check_readme(root, '<img src="missing.png">')

    def test_markdown_image_remains_checked(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(AssertionError):
                check_readme(d, '![Logo](missing.png)')

    def test_links_and_fragments(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'docs').mkdir()
            (root / 'docs/guide.md').write_text('guide')
            check_readme(root, '[Guide](docs/guide.md#start) [Section](#section) <a href="https://example.com">Web</a>')
            with self.assertRaises(AssertionError):
                check_readme(root, '[Guide](missing.md)')

    def test_local_target_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'project'
            root.mkdir()
            (root.parent / 'outside.png').write_bytes(b'fixture')
            with self.assertRaises(AssertionError):
                check_readme(root, '<img src="../outside.png">')



if __name__ == '__main__':
    unittest.main(verbosity=2)
