#!/usr/bin/env python3
"""Local repository audit. Reports paths and issue types, never credential values."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from provider_common import ROOT, KEY_GROUPS, SAFE_SETTINGS, config, safety_errors

PATTERNS = {
    'OpenAI-style key': re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b'),
    'Alpaca-style key ID': re.compile(rb'\b[AP]K[A-Z0-9]{18}\b'),
    'private PEM block': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'literal bearer token': re.compile(rb'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}'),
    'JWT token': re.compile(rb'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),
    'Coinbase credential name': re.compile(rb'organizations/[A-Za-z0-9-]{8,}/apiKeys/[A-Za-z0-9-]{8,}'),
    'literal credential assignment': re.compile(
        rb'''(?im)^[\t ]*["']?(?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|API_SECRET|BEARER_TOKEN|ACCESS_TOKEN|PRIVATE_KEY)["']?[\t ]*[:=][\t ]*["']?[A-Za-z0-9_+/=-]{24,}["']?[\t ]*[,;]?[\t ]*$'''),
}


def secret_types(data, known_values=()):
    kinds = {name for name, pattern in PATTERNS.items() if pattern.search(data)}
    if any(value and value in data for value in known_values):
        kinds.add('configured credential copied outside protected storage')
    return kinds


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True)


def protected_name(path):
    p = Path(path)
    return ((p.name.startswith('.env') and p.name != '.env.example')
            or 'secrets' in p.parts or '.venv' in p.parts
            or any(part in p.parts for part in ('data','node_modules','.next','.codex','.openai','credentials'))
            or p.name in ('service_key.json','credentials.json','.npmrc','.envrc')
            or p.suffix in ('.pem', '.key', '.p8', '.secret','.p12','.pfx','.jks','.keystore','.db','.sqlite','.sqlite3','.pkl','.pickle','.joblib','.safetensors'))


def audit_repository():
    issues = set()
    rev = git('rev-parse', '--show-toplevel')
    if rev.returncode or Path(os.fsdecode(rev.stdout).strip()).resolve() != ROOT:
        return [('repository', 'TraderX must be its own Git root')], 0
    for path in ('.env', '.venv/', 'secrets/', 'secrets/kalshi_private.pem',
                 '.env.local', 'local.key', '.DS_Store', '__pycache__/probe.pyc',
                 'credentials.json','service_key.json','data/traderx.db','frontend/.env.local','frontend/node_modules/', 'data/model.joblib'):
        if git('check-ignore', '--no-index', '-q', path).returncode != 0:
            issues.add((path, 'sensitive or generated path is not ignored'))
    if git('check-ignore', '--no-index', '-q', '.env.example').returncode != 1:
        issues.add(('.env.example', 'safe example must not be ignored'))
    template = dotenv_values(ROOT / '.env.example', interpolate=False)
    local = dotenv_values(ROOT / '.env', interpolate=False)
    required = set(SAFE_SETTINGS) | {n for names in KEY_GROUPS.values() for n in names} | {
        'APP_ENV', 'ALLOW_BILLABLE_TESTS', 'REQUIRED_PROVIDERS', 'OPENAI_MODEL',
        'X_API_ENABLED', 'KALSHI_PRIVATE_KEY_PATH', 'COINBASE_PRIVATE_KEY_PATH'}
    for name in required - set(template):
        issues.add(('.env.example', 'missing variable name: ' + name))
    for name in set(local) - set(template):
        issues.add(('.env.example', 'missing local variable name: ' + name))
    for filename in ('.env', '.env.example'):
        seen = set()
        if not (ROOT / filename).exists():continue
        for line in (ROOT / filename).read_text().splitlines():
            match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
            if match:
                name = match.group(1)
                if name in seen:
                    issues.add((filename, 'duplicate variable name: ' + name))
                seen.add(name)
    for names in KEY_GROUPS.values():
        for name in names:
            if template.get(name):
                issues.add(('.env.example', 'credential/contact field must be blank: ' + name))
    for filename, values in (('.env', {**template,**local}), ('.env.example', template), ('process environment', config())):
        for issue in safety_errors(values):
            issues.add((filename, issue))
        if values.get('ALLOW_BILLABLE_TESTS') != 'false' or values.get('X_API_ENABLED') != 'false':
            issues.add((filename, 'zero-spend flags must remain disabled for this cleanup'))
    # New application settings may use safe template defaults without rewriting .env.
    known = set()
    for values in (local, config()):
        for names in KEY_GROUPS.values():
            for name in names:
                if name != 'SEC_USER_AGENT' and len(values.get(name) or '') >= 8:
                    known.add(values[name].encode())
    for name, value in config().items():
        if name.endswith(('API_KEY','API_SECRET','BEARER_TOKEN')) and len(value or '') >= 8:
            known.add(value.encode())
    if template.get('LOCAL_LLM_API_KEY'):
        issues.add(('.env.example', 'local API key must be blank'))
    # Detect accidentally copied PEM payloads even if their BEGIN/END lines were removed.
    for pem in (ROOT / 'secrets').glob('*.pem'):
        if not pem.is_symlink() and pem.is_file():
            data = pem.read_bytes()
            if b'PRIVATE KEY' in data:
                known.update(line for line in data.splitlines() if len(line) >= 32 and not line.startswith(b'-'))
    listing = git('ls-files', '--cached', '--others', '--exclude-standard', '-z')
    if listing.returncode:
        return [('repository', 'unable to enumerate Git candidate files')], 0
    candidates = {os.fsdecode(p) for p in listing.stdout.split(b'\0') if p}
    for name in candidates:
        if protected_name(name):
            issues.add((name, 'protected path is tracked or not excluded'))
        path = ROOT / name
        if path.is_symlink():
            issues.add((name, 'candidate symlink needs explicit review'))
            continue
        data_sources = []
        if path.is_file():
            data_sources.append(('working tree', path.read_bytes()))
        staged = git('show', ':' + name)
        if staged.returncode == 0:
            data_sources.append(('Git index', staged.stdout))
        for origin, data in data_sources:
            for kind in secret_types(data, known):
                issues.add((name, kind + ' in ' + origin))
    return sorted(issues), len(candidates)


def main():
    issues, count = audit_repository()
    if '--history' in sys.argv:
        history=git('rev-list','--objects','--all')
        if history.returncode:issues.append(('repository','unable to inspect local Git history'))
        else:
            seen=set()
            known=[value.encode() for name,value in config().items() if name.endswith(('API_KEY','API_SECRET','BEARER_TOKEN','API_KEY_NAME')) and len(value or '')>=8]
            for line in history.stdout.decode().splitlines():
                parts=line.split(' ',1)
                if len(parts)!=2:continue
                oid,name=parts
                if oid in seen:continue
                seen.add(oid)
                if protected_name(name):issues.append((name,'protected path exists in local Git history'))
                kind=git('cat-file','-t',oid)
                if kind.stdout.strip()!=b'blob':continue
                data=git('cat-file','blob',oid)
                for finding in secret_types(data.stdout,known):issues.append((name,finding+' in local Git history'))
    for path, kind in issues:
        print('REVIEW: ' + path + ': ' + kind + '; no automatic changes')
    print(f'Repository audit: {"FAIL" if issues else "PASS"}; {count} candidate files and staged contents checked')
    print('Checks: ignore rules, environment separation, disabled execution, known credentials and secret patterns.')
    print('Scope: local working tree and Git index'+(' plus reachable local history' if '--history' in sys.argv else '')+'; heuristic scan, not remote certification.')
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
