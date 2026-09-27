#!/usr/bin/env python3
"""Inspect the provider environment without changing credentials or contacting APIs."""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider_common import ROOT, KEY_GROUPS, config, private_path, safety_errors, validate_sec_contact
from dotenv import dotenv_values

PACKAGES = ('openai', 'alpaca-py', 'gs-quant', 'coinbase-advanced-py', 'httpx',
            'python-dotenv', 'cryptography', 'PyJWT')


def main():
    cfg = config()
    problems = safety_errors(cfg)
    warnings = []
    print('Python ' + sys.version.split()[0])
    if sys.version_info < (3, 11):
        problems.append('Python 3.11 or newer is required; use the included .venv')
    for package in PACKAGES:
        try:
            print(package + ' ' + version(package))
        except PackageNotFoundError:
            (warnings if package == 'openai' else problems).append('Missing optional SDK: ' + package if package == 'openai' else 'Missing dependency: ' + package)
    local = dotenv_values(ROOT / '.env', interpolate=False)
    expected = dotenv_values(ROOT / '.env.example', interpolate=False)
    for name in expected:
        if name not in local:
            warnings.append('Missing .env variable name: ' + name)
    for name in local:
        if name not in expected:
            warnings.append('Unrecognized .env variable name (value omitted)')
    for provider, names in KEY_GROUPS.items():
        missing = [n for n in names if not cfg.get(n)]
        print(provider + ': ' + ('NOT_CONFIGURED (' + ', '.join(missing) + ')' if missing else 'credential fields present; live test needed'))
        for name in names:
            value = cfg.get(name, '')
            if not value:
                continue
            if '\n' in value or '\r' in value or value.lower() in ('demo', 'your_api_key', 'changeme', 'replace_me'):
                problems.append(name + ': placeholder or malformed value')
            if name != 'SEC_USER_AGENT' and (any(ch.isspace() for ch in value) or len(value) < 8):
                problems.append(name + ': obviously malformed credential')
    if cfg.get('FRED_API_KEY') and not re.fullmatch(r'[a-z0-9]{32}', cfg['FRED_API_KEY']):
        problems.append('FRED_API_KEY: expected 32 lowercase alphanumeric characters')
    if cfg.get('SEC_USER_AGENT') and not validate_sec_contact(cfg['SEC_USER_AGENT']):
        problems.append('SEC_USER_AGENT: supply identifying name and a real contact email')
    if cfg.get('COINBASE_API_KEY_NAME') and not re.fullmatch(r'organizations/[^/\s]+/apiKeys/[^/\s]+', cfg['COINBASE_API_KEY_NAME']):
        problems.append('COINBASE_API_KEY_NAME: expected organizations/.../apiKeys/...')
    if cfg.get('ALLOW_BILLABLE_TESTS') != 'false':
        warnings.append('Billable-tests setting differs from the delivered zero-spend default')
    if cfg.get('X_API_ENABLED') != 'false':
        warnings.append('X enabled; no request runs without the separate billable-test opt-in')
    secret_dir = ROOT / 'secrets'
    if not secret_dir.is_dir():
        problems.append('secrets/ directory is missing')
    protected = [ROOT / '.env', secret_dir]
    if secret_dir.is_dir():
        protected.extend(secret_dir.rglob('*'))
    for path in protected:
        if path.is_symlink():
            problems.append('A protected path is a symlink; use a local protected file')
        elif not path.exists():
            problems.append('A required protected path is missing')
        elif os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) & 0o077:
            problems.append('Protected file/directory permissions allow group or other access')
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, ec
    for setting, id_name in [('KALSHI_PRIVATE_KEY_PATH', 'KALSHI_API_KEY_ID'),
                             ('COINBASE_PRIVATE_KEY_PATH', 'COINBASE_API_KEY_NAME')]:
        if not cfg.get(id_name):
            continue
        try:
            key = serialization.load_pem_private_key(private_path(cfg, setting).read_bytes(), None)
            if setting.startswith('KALSHI'):
                valid = isinstance(key, ed25519.Ed25519PrivateKey) or (isinstance(key, rsa.RSAPrivateKey) and key.key_size >= 2048)
            else:
                valid = isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1)
            if not valid:
                problems.append(setting + ': incompatible key algorithm')
        except Exception:
            problems.append(setting + ': missing, invalid or insufficiently protected private key file')
    git = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if git.returncode:
        print('Git: workspace is not a repository; no tracked files exist here')
    else:
        git_root = Path(git.stdout.strip())
        tracked = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', '--', '.'], capture_output=True, check=True).stdout
        exposed = 0
        values = [cfg[n].encode() for names in KEY_GROUPS.values() for n in names
                  if n != 'SEC_USER_AGENT' and cfg.get(n) and len(cfg[n]) >= 8]
        for raw in tracked.split(b'\0'):
            if not raw:
                continue
            rel = Path(os.fsdecode(raw))
            path = ROOT / rel
            secret_name = ((rel.name.startswith('.env') and rel.name != '.env.example')
                           or 'secrets' in rel.parts or rel.suffix in ('.pem', '.key', '.p8', '.secret'))
            if secret_name:
                exposed += 1
            if path.is_file() and path.stat().st_size < 5_000_000:
                # Inspect Git's index too: a secret deleted only from the working copy remains staged.
                git_path = path.relative_to(git_root).as_posix()
                staged = subprocess.run(['git', '-C', str(git_root), 'show', ':' + git_path], capture_output=True)
                if any(value in staged.stdout or value in path.read_bytes() for value in values):
                    exposed += 1
        if exposed:
            problems.append('Git contains tracked/staged secret paths or configured credential values; remove from index and review history')
        else:
            print('Git: no tracked/staged configured secrets detected (full history not scanned)')
        from check_repository import audit_repository
        repository_issues, count = audit_repository()
        for path, kind in repository_issues:
            problems.append('Repository audit: ' + path + ': ' + kind)
        if not repository_issues:
            print(f'Repository audit: PASS; {count} candidate files plus staged contents checked')
    for warning in warnings:
        print('NOTE: ' + warning)
    for problem in problems:
        print('FAIL: ' + problem)
    print('Environment: ' + ('FAIL' if problems else 'PASS; unconfigured optional providers are listed above'))
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
