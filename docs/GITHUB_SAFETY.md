# Before publishing to GitHub

No repository push, publication or archive was performed by this build. The renamed
repository already contains an initial commit and a configured remote; both were
preserved. Existing commit metadata was checked for authoring-tool markers. No authoring-tool credit,
generator tag or co-author trailer was added. App page metadata identifies TraderX
only. Required optional-provider names and third-party licenses remain intact.

## Exclusions and checks

`.gitignore` excludes real environment files (including nested frontend env files),
secrets, private keys/certificates, credential JSON files, virtual environments,
node dependencies, builds, local databases, logs, cache, generated models, imported
CSV data and local tool folders. `.env.example` contains blank credential fields
and safe development defaults. `.dockerignore` excludes private runtime state.

Local pre-commit and pre-push hooks are installed. They scan candidate files and
staged bytes; the push hook also scans reachable local Git history for protected
paths and common secret patterns. The audit compares working/staged files against
configured credentials without printing them. It fails rather than deleting data.
These are useful safeguards, not a proof that every possible secret is detectable.

Before your first commit, run:

```sh
.venv/bin/python -B scripts/api_setup/check_repository.py --history
git status --short
```

Hooks are local Git configuration and do not propagate automatically to clones.
Install them on another checkout with:

```sh
.venv/bin/python scripts/install_git_hooks.py
```

Git ignore rules do not remove files already committed. If a check ever reports
a real credential in history, stop publishing, revoke that credential and clean
the affected history deliberately. Do not bypass the hook to get a push through.
Never place keys in frontend code or `NEXT_PUBLIC_*` variables. Keep `.env` and
`secrets/` local and maintain private backups separately from GitHub.

The launcher disables frontend framework telemetry. No public hosting or remote
access was enabled. This application is intended to bind to your Mac's loopback
interface; exposing it publicly requires authentication and deployment hardening.
