"""Offline regressions for repository secret scanning; all tokens are synthetic."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api_setup'))
import check_repository as audit


class RepositoryTests(unittest.TestCase):
    def test_blank_fields_do_not_consume_next_line(self):
        data = b'OPENAI_API_KEY=\nOPENAI_MODEL=a_configurable_model_name_long_enough\n'
        self.assertFalse(audit.secret_types(data))

    def test_provider_and_pem_patterns(self):
        fixtures = [b'sk-' + b'proj-' + b'X' * 32, b'PK' + b'1' * 18,
                    b'Bearer ' + b'a' * 32, b'-----BEGIN ' + b'PRIVATE KEY-----',
                    b'organizations/' + b'a' * 10 + b'/apiKeys/' + b'b' * 10,
                    b'API_SECRET=' + b'z' * 32]
        for data in fixtures:
            self.assertTrue(audit.secret_types(data))

    def test_known_opaque_credentials_are_detected(self):
        value = b'opaque-' + b'x' * 32
        self.assertTrue(audit.secret_types(b'value=' + value, (value,)))

    def test_template_is_safe(self):
        self.assertFalse(audit.secret_types((audit.ROOT / '.env.example').read_bytes()))

    def test_secret_only_in_index_is_detected(self):
        scratch = audit.ROOT / 'tmp'
        scratch.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=scratch) as folder:
                root = Path(folder)
                for name in ('.gitignore', '.env.example'):
                    (root / name).write_bytes((audit.ROOT / name).read_bytes())
                (root / '.env').write_bytes((root / '.env.example').read_bytes())
                (root / 'secrets').mkdir()
                def git(*args):
                    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
                git('init', '-b', 'main')
                (root / 'sample.txt').write_bytes(b'sk-' + b'proj-' + b'X' * 32)
                git('add', 'sample.txt')
                (root / 'sample.txt').write_text('working copy cleaned\n')
                with patch.object(audit, 'ROOT', root):
                    issues, _ = audit.audit_repository()
                self.assertTrue(any(path == 'sample.txt' and 'Git index' in kind for path, kind in issues))
                self.assertFalse(any(path == 'sample.txt' and 'working tree' in kind for path, kind in issues))
        finally:
            if not any(scratch.iterdir()):
                scratch.rmdir()


if __name__ == '__main__':
    unittest.main()
