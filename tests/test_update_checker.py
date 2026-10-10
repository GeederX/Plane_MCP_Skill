import importlib.util
import tempfile
import unittest
from pathlib import Path

from packaging.version import Version

CHECKER = Path(__file__).resolve().parents[1] / ".github/scripts/check_plane_update.py"
spec = importlib.util.spec_from_file_location("check_plane_update", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def metadata(*versions):
    return {"releases": {version: [{"yanked": False}] for version in versions}}


class ReleaseSelectionTests(unittest.TestCase):
    def test_numeric_version_order(self):
        self.assertEqual(checker.latest_release(metadata("0.3.9", "0.3.10", "0.3.4")), Version("0.3.10"))

    def test_skip_prerelease_dev_local_yanked_and_empty_releases(self):
        data = metadata("0.3.4", "1.0.0rc1", "1.0.0.dev1", "1.0.0+local", "invalid")
        data["releases"]["0.4.0"] = [{"yanked": True}]
        data["releases"]["0.5.0"] = []
        self.assertEqual(checker.latest_release(data), Version("0.3.4"))

    def test_release_with_one_non_yanked_file_is_available(self):
        data = metadata("0.3.4")
        data["releases"]["0.3.5"] = [{"yanked": True}, {"yanked": False}]
        self.assertEqual(checker.latest_release(data), Version("0.3.5"))

    def test_no_usable_releases_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "no stable"):
            checker.latest_release(metadata("1.0.0rc1"))


class UpdateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "client.py"
        self.source.write_text('SERVER = "plane-mcp-server==0.3.4"\n', encoding="utf-8")

    def test_apply_changes_effective_pin_and_second_run_is_noop(self):
        releases = metadata("0.3.4", "0.3.5")
        result = checker.check_update(self.source, releases, apply=True)
        self.assertTrue(result["applied"])
        namespace = {}
        exec(compile(self.source.read_text(), str(self.source), "exec"), namespace)
        self.assertEqual(namespace["SERVER"], "plane-mcp-server==0.3.5")
        again = checker.check_update(self.source, releases, apply=True)
        self.assertFalse(again["update_available"])
        self.assertFalse(again["applied"])

    def test_dry_run_does_not_modify_file(self):
        before = self.source.read_bytes()
        result = checker.check_update(self.source, metadata("0.3.5"))
        self.assertTrue(result["update_available"])
        self.assertFalse(result["applied"])
        self.assertEqual(self.source.read_bytes(), before)

    def test_no_downgrade(self):
        before = self.source.read_bytes()
        result = checker.check_update(self.source, metadata("0.3.3"), apply=True)
        self.assertFalse(result["update_available"])
        self.assertEqual(self.source.read_bytes(), before)

    def test_ambiguous_pin_fails_without_writing(self):
        self.source.write_text('A = "plane-mcp-server==0.3.4"\nB = "plane-mcp-server==0.3.5"\n')
        before = self.source.read_bytes()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            checker.check_update(self.source, metadata("0.3.6"), apply=True)
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
