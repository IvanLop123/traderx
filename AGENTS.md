# TraderX workspace rules

This directory is the single permanent project/repository root. Add future work
directly here. Do not create nested TraderX roots, phase repositories, exported
working copies, or ZIP-based collaboration workflows.

The user authorized the main application build in this existing repository.
The original Phase 0 API setup remains supported alongside the application.
Preserve provider scripts, docs, local .env, secrets, and the healthy virtual
environment. Read docs/BUILD_STATUS.md for implemented scope and remaining work.

Never print or commit credentials. Real values belong only in .env or secrets/;
.env.example must contain blank credential fields and safe defaults. Do not
overwrite or regenerate existing keys. Keep execution flags disabled and Alpaca
paper-only. Never submit orders or transfers during setup or verification.

Run ./check_environment.command and ./test_apis.command after provider setup
changes. Missing optional keys are not a build blocker; do not mislabel them as
successful authentication. Paid tests require separate explicit user approval.

Before staging or sharing, run:

    .venv/bin/python -B scripts/api_setup/check_repository.py

Use Git for collaboration. Do not push, publish, or create an archive unless the
user asks. Keep the local runtime and secrets outside version control.
