#!/usr/bin/env python3
"""Offline bundle layout regressions; the synthetic CLI is never executed."""
import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest

from package_release_bundle import BundleError, ROOT, create_bundle, main


SENTINEL = b"SYNTHETIC NONEXECUTED CLI SENTINEL\x00\xff\r\n"


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.cli = self.base / "synthetic-cli"
        self.cli.write_bytes(SENTINEL)
        self.cli.chmod(0o755)
        self.out = self.base / "new-parent" / "bundle"
        self.fixture = {
            "README.md": b'[Guide](docs/README.md) <img alt="logo" src="docs/assets/logo.png">\n',
            "LICENSE": b"license\n",
            "CHANGELOG.md": b"[Guide](docs/README.md)\r\n",
            "CITATION.cff": b"title: Fixture\n",
            "validation/README.md": b"[Metrics](../docs/METRIC_REGISTRY.md)\n",
            "MVS_Report_Pack_v1.0.0.mvsplugin": b"\x00plugin\xff",
            "docs/README.md": b"[Validation](../validation/README.md) [History](../benchmark_history/)\n",
            "docs/METRIC_REGISTRY.md": b"\xef\xbb\xbfRegistry\r\n",
            "docs/assets/logo.png": b"\x89PNG\r\n\x00\xfffixture",
            "examples/input.csv": b"entity,value\n1,2\n",
            "notebooks/example.ipynb": b'{"cells": []}\n',
            "benchmark_history/old/checkpoint.zip": b"archived bytes\x00\xff",
            "benchmark_history/old/report.md": b"Historical evidence.\n",
            "plugin-example-source/plugin.json": b"{}\n",
            "plugin-report-pack-source/README.md": b"[Plugin](../MVS_Report_Pack_v1.0.0.mvsplugin)\n",
            "plugin-report-pack-source/plugin.json": b"{}\n",
            "plugin-lab-pack-source/plugin.json": b"{}\n",
            "plugin-stress-pack-source/plugin.json": b"{}\n",
        }
        for relative, content in self.fixture.items():
            self.write(relative, content)

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return path

    def bundle(self, **kwargs):
        return create_bundle(kwargs.get("root", self.root), kwargs.get("cli", self.cli),
                             kwargs.get("out", self.out))

    def rejected(self, pattern, **kwargs):
        with self.assertRaisesRegex(BundleError, pattern):
            self.bundle(**kwargs)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.out.parent.exists(), "Preflight must not create output parents")

    def test_complete_fixture_bytes_and_cli_mode(self):
        result = self.bundle()
        actual = {str(path.relative_to(self.out)): path.read_bytes()
                  for path in self.out.rglob("*") if path.is_file()}
        self.assertEqual(actual, {**self.fixture, "mvs": SENTINEL})
        self.assertEqual(result.files, len(self.fixture) + 1)
        self.assertEqual(result.markdown_files, 7)
        self.assertEqual(result.local_links, 7)
        self.assertEqual(stat.S_IMODE((self.out / "mvs").stat().st_mode), 0o755)

    def test_future_checkpoint_and_assets_are_automatically_preserved(self):
        self.write("docs/ROUND999_NEW_CHECKPOINT.md", "[Data](assets/future.dat)")
        self.write("docs/assets/future.dat", b"\x00future\xff")
        self.bundle()
        self.assertEqual((self.out / "docs/ROUND999_NEW_CHECKPOINT.md").read_bytes(),
                         b"[Data](assets/future.dat)")
        self.assertEqual((self.out / "docs/assets/future.dat").read_bytes(), b"\x00future\xff")

    def test_selected_empty_directories_are_preserved(self):
        (self.root / "docs/assets/empty").mkdir()
        self.bundle()
        self.assertTrue((self.out / "docs/assets/empty").is_dir())

    def test_missing_required_tree_fails_before_writes(self):
        (self.root / "plugin-example-source/plugin.json").unlink()
        (self.root / "plugin-example-source").rmdir()
        self.rejected("Missing required source")

    def test_missing_root_readme_fails_before_writes(self):
        (self.root / "README.md").unlink()
        self.rejected("Missing required source")

    def test_missing_docs_tree_fails_before_writes(self):
        (self.root / "docs").rename(self.base / "saved-docs")
        self.rejected("Missing required source")

    def test_required_directory_cannot_be_a_file(self):
        (self.root / "plugin-example-source/plugin.json").unlink()
        (self.root / "plugin-example-source").rmdir()
        self.write("plugin-example-source", b"not a directory")
        self.rejected("Expected source directory")

    def test_missing_markdown_target_fails_before_writes(self):
        self.write("docs/future.md", "[Checkpoint](MISSING.md)")
        self.rejected("Missing bundled link target")

    def test_missing_markdown_image_fails_before_writes(self):
        self.write("docs/future.md", "![Image](assets/MISSING.png)")
        self.rejected("Missing bundled link target")

    def test_missing_html_image_fails_before_writes(self):
        self.write("README.md", '<IMG width="32" alt="logo" src="docs/assets/MISSING.png" />')
        self.rejected("Missing bundled link target")

    def test_missing_reference_destination_fails_before_writes(self):
        self.write("docs/future.md", "[Checkpoint][round]\n\n[round]: MISSING.md 'Title'\n")
        self.rejected("Missing bundled link target")

    def test_links_inside_every_copied_markdown_tree_are_checked(self):
        for relative in ("examples/README.md", "notebooks/README.md",
                         "benchmark_history/old/report.md", "plugin-lab-pack-source/README.md",
                         "validation/README.md"):
            with self.subTest(document=relative):
                path = self.write(relative, "[Missing](MISSING.md)")
                self.rejected("Missing bundled link target")
                path.write_text("No links.\n", encoding="utf-8")

    def test_link_to_existing_unselected_source_fails(self):
        self.write("private/secret.txt", b"not a release input")
        self.write("docs/future.md", "[Private](../private/secret.txt)")
        self.rejected("Missing bundled link target")

    def test_local_link_cannot_escape_bundle(self):
        (self.base / "outside.md").write_text("outside")
        for target in ("../outside.md", "%2e%2e/outside.md", "/outside.md",
                       "file:///outside.md", r"C:\outside.md", "docs/%00.md",
                       "docs/%5c../outside.md"):
            with self.subTest(target=target):
                self.write("README.md", f"[Outside]({target})")
                self.rejected("Unsafe local link|escapes bundle")

    def test_supported_local_links_and_external_urls(self):
        self.write("docs/assets/space name(1).png", b"image")
        self.write("docs/links.md", """[Inline](assets/space%20name(1).png "Title")
![Angle](<assets/space name(1).png>)
[Escaped](assets/space%20name\\(1\\).png)
[Reference][image] ![Collapsed][] [Shortcut]
[image]: assets/space%20name(1).png
[Collapsed]: <assets/space name(1).png> "Title"
[Shortcut]: assets/logo.png
[Parent](../LICENSE#license) [Directory](../benchmark_history/)
[External](https://example.org/no-such-file) [Mail](mailto:user@example.org)
[Network](//example.org/path) [Fragment](#heading) [Query](?view=1#heading)
<a href="../LICENSE">License</a><img src="assets/logo.png" />
""")
        self.bundle()

    def test_code_examples_are_not_treated_as_links(self):
        self.write("docs/code.md", """`[Example](MISSING.md)`
```markdown
![Example](MISSING.png)
```
~~~html
<img src="MISSING.png">
~~~
""")
        self.bundle()

    def test_source_leaf_symlink_rejected_even_with_in_scope_target(self):
        path = self.root / "docs/assets/alias.png"
        path.symlink_to(self.root / "docs/assets/logo.png")
        self.rejected("Symlink")

    def test_source_tree_symlink_rejected(self):
        path = self.root / "docs/external"
        path.symlink_to(self.base, target_is_directory=True)
        self.rejected("Symlink")

    def test_selected_file_parent_symlink_rejected(self):
        (self.root / "validation/README.md").unlink()
        (self.root / "validation").rmdir()
        support = self.base / "external-validation"
        support.mkdir()
        (support / "README.md").write_text("outside")
        (self.root / "validation").symlink_to(support, target_is_directory=True)
        self.rejected("Symlink")

    def test_source_root_parent_alias_rejected(self):
        alias = self.base / "alias"
        alias.symlink_to(self.base, target_is_directory=True)
        self.rejected("Symlink", root=alias / "source")

    def test_cli_leaf_and_parent_aliases_rejected(self):
        leaf = self.base / "cli-alias"
        leaf.symlink_to(self.cli)
        self.rejected("Symlink", cli=leaf)
        parent = self.base / "parent-alias"
        parent.symlink_to(self.base, target_is_directory=True)
        self.rejected("Symlink", cli=parent / self.cli.name)

    def test_missing_cli_and_directory_cli_rejected(self):
        self.rejected("Missing required source", cli=self.base / "missing-cli")
        self.rejected("CLI must be a regular file", cli=self.root)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX named pipes")
    def test_special_source_file_rejected_without_reading_it(self):
        os.mkfifo(self.root / "docs/pipe")
        self.rejected("not a regular file or directory")

    def test_existing_output_is_never_modified(self):
        self.out.mkdir(parents=True)
        marker = self.out / "keep.txt"
        marker.write_bytes(b"existing data")
        with self.assertRaisesRegex(BundleError, "already exists"):
            self.bundle()
        self.assertEqual(marker.read_bytes(), b"existing data")
        self.assertEqual(list(self.out.iterdir()), [marker])

    def test_existing_empty_output_is_rejected(self):
        self.out.mkdir(parents=True)
        with self.assertRaisesRegex(BundleError, "already exists"):
            self.bundle()
        self.assertEqual(list(self.out.iterdir()), [])

    def test_output_leaf_and_parent_symlinks_rejected(self):
        leaf = self.base / "dangling-output"
        leaf.symlink_to(self.base / "missing")
        self.rejected("Symlink", out=leaf)
        alias = self.base / "output-alias"
        alias.symlink_to(self.root / "docs", target_is_directory=True)
        self.rejected("Symlink", out=alias / "bundle")
        self.assertFalse((self.root / "docs/bundle").exists())

    def test_output_inside_selected_input_tree_is_rejected(self):
        self.rejected("inside a selected source tree", out=self.root / "docs/new-bundle")
        self.assertFalse((self.root / "docs/new-bundle").exists())

    def test_output_equal_to_or_containing_input_preserves_input(self):
        for out in (self.root, self.root / "docs", self.base, self.cli):
            with self.subTest(output=out):
                self.rejected("already exists|overlaps", out=out)
        self.assertEqual(self.cli.read_bytes(), SENTINEL)
        self.assertEqual((self.root / "README.md").read_bytes(), self.fixture["README.md"])

    def test_output_parent_file_fails_before_writes(self):
        self.rejected("Output parent is not a directory", out=self.cli / "bundle")
        self.assertEqual(self.cli.read_bytes(), SENTINEL)

    def test_regular_staging_directory_inside_root_is_allowed(self):
        out = self.root / "staging/bundle"
        self.bundle(out=out)
        self.assertEqual((out / "mvs").read_bytes(), SENTINEL)

    def test_only_machine_cache_directories_are_omitted(self):
        self.write("notebooks/__pycache__/local.pyc", b"machine cache")
        self.write("docs/assets/__pycache__", b"a real source file with this name")
        self.write("docs/assets/obj/source.bin", b"source asset")
        self.write("docs/assets/.hidden", b"source asset")
        self.bundle()
        self.assertFalse((self.out / "notebooks/__pycache__").exists())
        for relative in ("docs/assets/__pycache__", "docs/assets/obj/source.bin", "docs/assets/.hidden"):
            self.assertEqual((self.out / relative).read_bytes(), (self.root / relative).read_bytes())

    def test_unselected_trees_are_not_traversed_or_copied(self):
        for name in ("private", "bin", "obj", "python", "validation/unselected"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(self.base, target_is_directory=True)
        self.bundle()
        for name in ("private", "bin", "obj", "python", "validation/unselected"):
            self.assertFalse((self.out / name).exists())

    def test_command_line_success_and_failure(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            main(["--root", str(self.root), "--cli", str(self.cli), "--out", str(self.out)])
        self.assertIn("CLI copied without execution", output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as caught:
                main(["--root", str(self.root), "--cli", str(self.cli), "--out", str(self.out)])
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("already exists", error.getvalue())

    def test_actual_repository_layout_with_nonexecuted_synthetic_cli(self):
        result = self.bundle(root=ROOT)
        self.assertEqual((self.out / "mvs").read_bytes(), SENTINEL)
        for relative in ("README.md", "docs/assets/logo.png", "docs/METRIC_REGISTRY.md",
                         "docs/CALIBRATION_RECOMMENDATIONS.md", "docs/ROUND15_PROJECT_READINESS_AUDIT.md",
                         "validation/README.md", "MVS_Report_Pack_v1.0.0.mvsplugin"):
            self.assertEqual((self.out / relative).read_bytes(), (ROOT / relative).read_bytes())
        for name in ("docs", "benchmark_history", "examples", "notebooks", "plugin-example-source",
                     "plugin-report-pack-source", "plugin-lab-pack-source", "plugin-stress-pack-source"):
            expected = {path.relative_to(ROOT) for path in (ROOT / name).rglob("*")
                        if path.is_file() and "__pycache__" not in path.relative_to(ROOT).parts[:-1]}
            actual = {path.relative_to(self.out) for path in (self.out / name).rglob("*") if path.is_file()}
            self.assertEqual(actual, expected)
            for relative in expected:
                self.assertEqual((self.out / relative).read_bytes(), (ROOT / relative).read_bytes())
        self.assertGreater(result.markdown_files, 35)
        self.assertGreater(result.local_links, 50)
        self.assertFalse((self.out / "python").exists())
        self.assertFalse((self.out / "Core").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
