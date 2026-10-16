"""Preparation guard tests only: never invoke either numerical implementation."""
from pathlib import Path
import tempfile
import unittest
from prepare_normal_tail_native import (
    ANALYSIS, CORE_PROJECT, ORIGINAL_RETURN, CANDIDATE_RETURN,
    assert_copy_changes, candidate_project, candidate_source, source_files,
)


class NativePreparationTests(unittest.TestCase):
    def source(self, expression=ORIGINAL_RETURN):
        return b"namespace MvsAnalyzer;\ninternal static double MannWhitneyP(double[] a, double[] b)\n{\n" + expression + b"\n}\nprivate static double NormalCdf(double z)\n{ return z; }\n"

    def test_exact_single_expression(self):
        original = self.source()
        changed = candidate_source(original)
        self.assertEqual(changed.replace(CANDIDATE_RETURN, ORIGINAL_RETURN), original)
        self.assertEqual(changed.count(CANDIDATE_RETURN), 1)

    def test_no_match_refused(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            candidate_source(self.source(b"return 1;"))

    def test_duplicate_match_refused(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            candidate_source(self.source() + ORIGINAL_RETURN)

    def test_wrong_method_refused(self):
        with self.assertRaisesRegex(ValueError, "boundary"):
            candidate_source(self.source().replace(b"MannWhitneyP", b"UnrelatedMethod"))

    def test_temporary_project_reversible(self):
        original = b'<Project Sdk="Microsoft.NET.Sdk">\r\n</Project>\r\n'
        changed = candidate_project(original)
        self.assertIn(b'Version="[5.0.0]"', changed)
        self.assertNotIn(b"\n", changed.replace(b"\r\n", b""))
        with self.assertRaises(ValueError):
            candidate_project(changed)

    def test_unexpected_changes_refused(self):
        original = {ANALYSIS: "old", CORE_PROJECT: "old", "Core/Other.cs": "old"}
        expected = dict(original, **{ANALYSIS: "new", CORE_PROJECT: "new"})
        assert_copy_changes(original, expected, {ANALYSIS, CORE_PROJECT})
        expected["Core/Other.cs"] = "new"
        with self.assertRaisesRegex(ValueError, "Unexpected source"):
            assert_copy_changes(original, expected, {ANALYSIS, CORE_PROJECT})

    def test_source_manifest_excludes_only_named_generated_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Core").mkdir()
            (root / "Core" / "A.cs").write_text("frozen")
            (root / "Core" / "bin").mkdir()
            (root / "Core" / "bin" / "build.dll").write_bytes(b"generated")
            (root / "Assets").mkdir()
            (root / "Assets" / "payload.zip").write_bytes(b"source-controlled payload")
            self.assertEqual(set(source_files(root)), {"Core/A.cs", "Assets/payload.zip"})

    def test_path_set_change_refused(self):
        with self.assertRaisesRegex(ValueError, "paths differ"):
            assert_copy_changes({"a": "x"}, {"a": "x", "b": "y"}, set())


if __name__ == "__main__":
    unittest.main()
