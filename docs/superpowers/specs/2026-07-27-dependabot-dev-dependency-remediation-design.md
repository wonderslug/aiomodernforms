# Dependabot Dev-Dependency Remediation

## Problem

The [Dependabot alerts page](https://github.com/wonderslug/aiomodernforms/security/dependabot) lists 10 open alerts (as of 2026-07-27). All 10 are in dev/test tooling — `requirements_dev.txt` and `requirements_test.txt` — not in `requirements.txt` (the library's actual runtime dependencies: `aiohttp`, `backoff`, `yarl`). Library users are not exposed; this is about hardening the project's own dev/CI environment.

Alerts, by affected package:

| Package | Manifest | Current | Alerts (severity) |
|---|---|---|---|
| pip | requirements_dev.txt | 23.1.2 | #13 path traversal (medium), #12 untrusted functionality (medium), #11 tar/zip confusion (medium), #8 path traversal (low), #6 symlink tar extraction (medium), #2 command injection (medium) |
| black | requirements_dev.txt | 23.3.0 | #9 arbitrary file write (high), #3 ReDoS (medium) |
| wheel | requirements_dev.txt | 0.37.1 | #4 ReDoS (high) |
| pytest | requirements_test.txt | 7.4.0 | #10 insecure tmpdir handling (medium) |

## Scope

Full dev-tooling refresh: close all flagged alerts, bump the pytest companion packages for compatibility, and additionally sync every other pinned dev-tool version (in `.pre-commit-config.yaml` and `requirements_test.txt`) that has drifted, since several are stale enough to already be inconsistent between the two files.

Out of scope:
- `requirements.txt` (aiohttp, backoff, yarl) — no alerts, no change.
- GitHub Actions pins (`actions/checkout`, `actions/setup-python`, `codecov-action`) — not a Dependabot dependency alert.
- `aresponses` — already at latest (3.0.0).

## Version Targets

**Security-flagged:**

| Package | Current | Target |
|---|---|---|
| pip | 23.1.2 | 26.1.2 |
| black | 23.3.0 | 26.5.1 |
| wheel | 0.37.1 | 0.47.0 |
| pytest | 7.4.0 | 9.1.1 |

**Pytest companions** (compatibility with pytest 9.x):

| Package | Current | Target |
|---|---|---|
| pytest-asyncio | 0.21.0 | 1.4.0 |
| pytest-cov | 4.1.0 | 7.1.0 |

**Other dev-tooling refresh:**

| Package | Current | Target |
|---|---|---|
| autopep8 | 1.6.0 | 2.3.2 |
| blacken-docs | 1.14.0 | 1.20.0 |
| pre-commit | 3.3.3 | 4.6.1 |
| twine | 4.0.2 | 7.0.0 |
| yamllint | 1.26.3 | 1.38.0 |
| coverage | 7.2.7 | 7.15.2 |
| flake8 | 4.0.1 | 7.3.0 |
| flake8-docstrings | 1.6.0 | 1.7.0 |
| isort | 5.11.5 | 8.0.1 |
| mypy | 1.4.1 | 2.3.0 |
| pylint | 2.15.10 | 4.0.6 |
| pyupgrade (pre-commit only) | v2.7.2 | v3.21.2 |

`.pre-commit-config.yaml` revs are synced to match: black, blacken-docs' embedded `black==` dependency, isort, pylint, mypy, flake8, yamllint, autopep8, pyupgrade, plus the generic `pre-commit/pre-commit-hooks` and `pre-commit/pre-commit` (validate_manifest) mirrors bumped to their current releases. `pyupgrade`'s `--py36-plus` becomes `--py311-plus`, and black's `--target-version` becomes `py311`, matching `setup.py`'s `python_requires>=3.11`.

## Execution Strategy

Several of these tools jump multiple major versions (isort 5→8, pylint 2→4, mypy 1→2, flake8 4→7). Each can surface new lint rules, deprecations, or reformatting that flags pre-existing issues in the source — distinct from the mechanical act of bumping a pinned version. To keep those concerns separable in review, this lands as two staged commits on one branch, in order of increasing risk:

1. **Security-critical bump** — pip, black, wheel, pytest, pytest-asyncio, pytest-cov, plus the black rev/target-version sync in `.pre-commit-config.yaml`. Black 26.x reformatting is the expected fallout here; commit it as-is.
2. **Remaining tooling refresh** — isort, flake8(+docstrings), pylint, mypy, autopep8, pyupgrade, coverage, pre-commit, twine, blacken-docs, yamllint. Any lint/type errors newly surfaced get fixed in source as their own reviewable diff, separate from the version-bump diff.

If stage 2 needs to be unwound later, stage 1 (the actual security fixes) remains intact independently.

## Verification

After each stage:
- `pre-commit run --all-files --show-diff-on-failure`
- `pytest --cov=aiomodernforms --cov-report=xml`

Run on the Python versions in the CI matrix (3.11, 3.12), mirroring `.github/workflows/ci.yml`.

## Risks

- Black's 3-major-version jump may produce a large reformatting diff across the whole codebase (expected, accepted).
- pylint 2→4 and mypy 1→2 may introduce new checks that fail on existing code; these get fixed as real (if minor) code changes in stage 2, not suppressed.
- pytest 7→9 with pytest-asyncio 0.21→1.4 may require fixture/marker syntax updates if any deprecated APIs are in use.
