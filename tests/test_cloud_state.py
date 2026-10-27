"""Exercise actual git restore/publish with a local bare remote, no credentials."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


class CloudStateTests(unittest.TestCase):
    def test_source_branch_preserved_state_restored_and_rewrites_blocked(self):
        source = Path(__file__).resolve().parents[1] / "scripts" / "cloud_state.py"
        spec = importlib.util.spec_from_file_location("test_cloud_state_module", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix="moex-state-test-") as folder:
            root, remote = Path(folder) / "code", Path(folder) / "remote.git"
            root.mkdir()
            def git(*args, cwd=root):
                return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout
            git("init", "--bare", str(remote))
            git("init", "-b", "main")
            git("config", "user.name", "Test Author")
            git("config", "user.email", "test@example.invalid")
            git("remote", "add", "origin", str(remote))
            (root / "source.txt").write_text("Preserve source branch\n")
            git("add", "source.txt")
            git("commit", "-m", "Test source")
            git("push", "origin", "main")
            original_head = git("rev-parse", "HEAD").strip()
            module.ROOT = root
            module.restore()
            state = root / "cloud_state"
            state.mkdir()
            ledger = state / "forecasts.jsonl"
            ledger.write_text('{"forecast_id":"first"}\n')
            report = root / "cloud_reports"
            report.mkdir()
            (report / "latest.md").write_text("Test report\n")
            module.publish()
            self.assertEqual(git("rev-parse", "HEAD").strip(), original_head)
            self.assertEqual(git("show", "origin/main:source.txt"), "Preserve source branch\n")
            self.assertEqual(git("show", "refs/heads/moex-data:cloud_state/forecasts.jsonl"), ledger.read_text())
            ledger.unlink()
            module.restore()
            self.assertEqual(ledger.read_text(), '{"forecast_id":"first"}\n')
            with ledger.open("a") as stream:
                stream.write('{"forecast_id":"second"}\n')
            module.publish()
            ledger.write_text('{"forecast_id":"rewritten"}\n')
            with self.assertRaisesRegex(RuntimeError, "non-append"):
                module.publish()


if __name__ == "__main__":
    unittest.main()
