import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'agent_claims.py'
INSTALLER = SCRIPT.with_name('install_agent_claims.py')


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), *args],
                              capture_output=True, text=True)

    def test_reject_same_file_atomic_and_leave_other_claim(self):
        first = self.run_cli('claim', '--agent', 'codex', '--plan', 'score', '--target', 'src/a.py')
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_cli('claim', '--agent', 'pi', '--plan', 'rank', '--target', 'src/a.py')
        self.assertEqual(second.returncode, 2)
        state = json.loads((self.root / '.agent-coordination/claims.json').read_text())
        self.assertEqual(set(state['claims']), {'codex'})

    def test_allow_distinct_symbols_only_if_both_opt_in(self):
        a = self.run_cli('claim', '--agent', 'a', '--plan', 'left', '--target', 'src/a.py::foo', '--allow-disjoint-symbols')
        self.assertEqual(a.returncode, 0, a.stderr)
        b = self.run_cli('claim', '--agent', 'b', '--plan', 'right', '--target', 'src/a.py::bar')
        self.assertEqual(b.returncode, 2)
        c = self.run_cli('claim', '--agent', 'b', '--plan', 'right', '--target', 'src/a.py::bar', '--allow-disjoint-symbols')
        self.assertEqual(c.returncode, 0, c.stderr)
        d = self.run_cli('claim', '--agent', 'c', '--plan', 'nested', '--target', 'src/a.py::foo.bar', '--allow-disjoint-symbols')
        self.assertEqual(d.returncode, 2)

    def test_release_and_check(self):
        self.assertEqual(self.run_cli('claim', '--agent', 'a', '--plan', 'x', '--target', 'x.py').returncode, 0)
        self.assertEqual(self.run_cli('check', '--agent', 'a', '--target', 'x.py::foo').returncode, 0)
        self.assertEqual(self.run_cli('check', '--agent', 'b', '--target', 'x.py').returncode, 2)
        self.assertEqual(self.run_cli('release', '--agent', 'a').returncode, 0)
        self.assertEqual(self.run_cli('claim', '--agent', 'b', '--plan', 'x', '--target', 'x.py').returncode, 0)

    def test_failed_update_keeps_existing_targets(self):
        self.assertEqual(self.run_cli('claim', '--agent', 'a', '--plan', 'A', '--target', 'a.py').returncode, 0)
        self.assertEqual(self.run_cli('claim', '--agent', 'b', '--plan', 'B', '--target', 'b.py').returncode, 0)
        bad = self.run_cli('claim', '--agent', 'a', '--plan', 'A2', '--target', 'a.py', '--target', 'b.py')
        self.assertEqual(bad.returncode, 2)
        state = json.loads((self.root / '.agent-coordination/claims.json').read_text())
        self.assertEqual(state['claims']['a']['plan'], 'A')
        self.assertEqual(len(state['claims']['a']['targets']), 1)

    def test_reject_path_escape(self):
        bad = self.run_cli('claim', '--agent', 'a', '--plan', 'x', '--target', '../outside.py')
        self.assertEqual(bad.returncode, 1)

    def test_aliases_conflict_and_can_check_or_release(self):
        actual = self.root / 'actual.py'
        actual.touch()
        (self.root / 'alias.py').symlink_to(actual)
        self.assertEqual(self.run_cli('claim', '--agent', 'a', '--plan', 'edit', '--target', 'alias.py').returncode, 0)
        rejected = self.run_cli('claim', '--agent', 'b', '--plan', 'edit', '--target', 'actual.py')
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertEqual(self.run_cli('check', '--agent', 'a', '--target', 'actual.py').returncode, 0)
        self.assertEqual(self.run_cli('release', '--agent', 'a', '--target', 'actual.py').returncode, 0)

    def test_directories_cannot_be_claimed(self):
        (self.root / 'src').mkdir()
        result = self.run_cli('claim', '--agent', 'a', '--plan', 'edit', '--target', 'src')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Target must be a file', result.stderr)

    def test_board_failure_preserves_success_and_can_be_repaired(self):
        board = self.root / '.agent-coordination' / 'ACTIVE_TASKS.md'
        board.mkdir(parents=True)
        result = self.run_cli('claim', '--agent', 'a', '--plan', 'edit', '--target', 'new.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('registry saved', result.stderr)
        self.assertEqual(self.run_cli('check', '--agent', 'a', '--target', 'new.py').returncode, 0)
        board.rmdir()
        refresh = self.run_cli('status', '--refresh-board')
        self.assertEqual(refresh.returncode, 0, refresh.stderr)
        self.assertIn('new.py', board.read_text())

    def test_invalid_registry_fails_cleanly_and_preserves_data(self):
        path = self.root / '.agent-coordination' / 'claims.json'
        path.parent.mkdir()
        for contents in ('[]', '{"schema": 1, "claims": {"a": {"targets": []}}}'):
            with self.subTest(contents=contents):
                path.write_text(contents)
                result = self.run_cli('claim', '--agent', 'b', '--plan', 'edit', '--target', 'new.py')
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('refusing to overwrite', result.stderr)
                self.assertEqual(path.read_text(), contents)

    def test_parallel_owners_one_winner(self):
        def attempt(i):
            return self.run_cli('claim', '--agent', f'a{i}', '--plan', 'race', '--target', 'src/race.py').returncode
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(results.count(0), 1)
        self.assertEqual(results.count(2), 7)


class InstallTests(unittest.TestCase):
    def test_installs_into_another_checkout_and_preserves_instructions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            agents = root / 'AGENTS.md'
            agents.write_bytes(b'# Existing rules\r\n')
            (root / '.gitignore').write_text('build/\n!/.agent-coordination/\n')
            result = self.install(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            cli = root / 'tools' / 'agent_claims.py'
            self.assertEqual(cli.read_bytes(), SCRIPT.read_bytes())
            first_install = agents.read_bytes()
            self.assertTrue(first_install.startswith(b'# Existing rules\r\n\r\n'))
            self.assertTrue((root / '.gitignore').read_text().endswith('/.agent-coordination/\n'))
            self.assertEqual(self.install(root).returncode, 0)
            self.assertEqual(agents.read_bytes(), first_install)
            status = subprocess.run([sys.executable, str(cli), 'status'], cwd=root, capture_output=True, text=True)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn('No active claims.', status.stdout)

    def test_refuses_to_replace_a_different_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cli = root / 'tools' / 'agent_claims.py'
            cli.parent.mkdir()
            cli.write_text('# Local script\n')
            result = self.install(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(cli.read_text(), '# Local script\n')
            self.assertFalse((root / 'AGENTS.md').exists())

    def install(self, root):
        return subprocess.run([sys.executable, str(INSTALLER), '--root', str(root)],
                              capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
