# Dependabot Dev-Dependency Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all 10 open Dependabot alerts (pip, black, wheel, pytest) and refresh every other stale dev-tool pin in `.pre-commit-config.yaml`/`requirements_test.txt`, without touching runtime dependencies.

**Architecture:** Two staged commits on this branch. Stage 1 bumps only the four Dependabot-flagged packages plus pytest's two companion packages (pytest-asyncio, pytest-cov) needed for compatibility, and syncs black's rev in `.pre-commit-config.yaml`. Stage 2 bumps every remaining stale dev-tool pin (isort, flake8, pylint, mypy, autopep8, pyupgrade, coverage, pre-commit, twine, blacken-docs, yamllint) and fixes any lint/type fallout those bumps surface, as its own diff.

**Tech Stack:** Python 3.11 (existing `.venv` at repo root, itself Python 3.11.15), pip, pre-commit, pytest.

## Global Constraints

- `requirements.txt` (aiohttp, backoff, yarl) is untouched — no Dependabot alerts target it.
- GitHub Actions pins in `.github/workflows/*.yml` are untouched — out of spec scope.
- `aresponses==3.0.0` in `requirements_test.txt` is already current — no change.
- Every version bump must land at or above the spec's target version (see spec's Version Targets tables) — never below the security-patched floor.
- `setup.py` already declares `python_requires=">=3.11"`; black's `--target-version` and pyupgrade's `--py*-plus` arg must match (`py311`).
- **Deviation from spec:** the spec listed `autopep8` target as `2.3.2` (latest PyPI release). The `pre-commit/mirrors-autopep8` hook repo that mirrors it has not been tagged past `v2.0.4` (confirmed via `git ls-remote --tags`), so the pre-commit hook cannot go higher than that. This plan pins `autopep8==2.0.4` in `requirements_dev.txt` (matching the mirror) instead of `2.3.2`, to keep the two files in sync. This is still a large jump up from the current `1.6.0` and is not a Dependabot-flagged package.

---

### Task 1: Stage 1 — security-critical bump (pip, black, wheel, pytest)

**Files:**
- Modify: `requirements_dev.txt`
- Modify: `requirements_test.txt`
- Modify: `.pre-commit-config.yaml`

**Interfaces:** N/A — this task only changes pinned dependency versions and a pre-commit hook config; there are no new functions, classes, or call sites for later tasks to consume.

- [ ] **Step 1: Update `requirements_dev.txt`**

Replace the full file contents with:

```
autopep8==1.6.0
black==26.5.1
blacken-docs==1.14.0
pip==26.1.2
pre-commit==3.3.3
twine==4.0.2
wheel==0.47.0
yamllint==1.26.3
```

(Only `black`, `pip`, and `wheel` change in this step; `autopep8`, `blacken-docs`, `pre-commit`, `twine`, `yamllint` stay as-is until Task 2.)

- [ ] **Step 2: Update `requirements_test.txt`**

Replace the full file contents with:

```
aresponses==3.0.0
coverage==7.2.7
flake8==4.0.1
flake8-docstrings==1.6.0
isort==5.11.5
mypy==1.4.1
pylint==2.15.10
pytest==9.1.1
pytest-asyncio==1.4.0
pytest-cov==7.1.0
```

(Only `pytest`, `pytest-asyncio`, `pytest-cov` change in this step; the rest stay as-is until Task 2.)

- [ ] **Step 3: Update `.pre-commit-config.yaml`**

Replace the full file contents with:

```yaml
---
repos:
  - repo: https://github.com/psf/black
    rev: 26.5.1
    hooks:
      - id: black
        args: [--safe, --quiet, --target-version, py311]
  - repo: https://github.com/adamchainz/blacken-docs
    rev: 1.14.0
    hooks:
      - id: blacken-docs
        additional_dependencies: [black==26.5.1]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v3.2.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-merge-conflict
      - id: debug-statements
      - id: check-docstring-first
      - id: check-json
      - id: check-yaml
      - id: requirements-txt-fixer
      - id: check-byte-order-marker
      - id: check-case-conflict
      - id: fix-encoding-pragma
        args: ["--remove"]
      - id: check-ast
      - id: detect-private-key
      - id: forbid-new-submodules
  - repo: https://github.com/pre-commit/pre-commit
    rev: v2.7.0
    hooks:
      - id: validate_manifest
  - repo: https://github.com/pre-commit/mirrors-autopep8
    rev: v1.5.4
    hooks:
      - id: autopep8
  - repo: https://github.com/PyCQA/isort
    rev: 5.12.0
    hooks:
      - id: isort
  - repo: https://github.com/pycqa/pylint
    rev: v2.15.10
    hooks:
      - id: pylint
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.4.1
    hooks:
      - id: mypy
  - repo: https://github.com/pycqa/flake8
    rev: 3.8.3
    hooks:
      - id: flake8
        additional_dependencies: ["flake8-docstrings"]
  - repo: https://github.com/adrienverge/yamllint.git
    rev: v1.24.2
    hooks:
      - id: yamllint
  - repo: https://github.com/asottile/pyupgrade
    rev: v2.7.2
    hooks:
      - id: pyupgrade
        args: [--py36-plus]
exclude: '^.github/.*'
```

(Only the `black` block's `rev`/`--target-version` and the `blacken-docs` block's `rev`/embedded `black==` version change in this step; every other repo block is untouched until Task 2.)

- [ ] **Step 4: Reinstall dependencies into the existing venv**

Run:
```bash
.venv/bin/pip install -r requirements_dev.txt -r requirements_test.txt -r requirements.txt
```
Expected: pip installs/upgrades `pip`, `black`, `wheel`, `pytest`, `pytest-asyncio`, `pytest-cov` (and their transitive deps) with no errors.

- [ ] **Step 5: Run pre-commit across all files and resolve fallout**

Run:
```bash
.venv/bin/pre-commit run --all-files --show-diff-on-failure
```
Expected: `black` (now 26.x, targeting `py311`) may reformat files under `aiomodernforms/` and `tests/` — this is expected and should be accepted as-is (do not hand-revert black's formatting choices). If the run reports failures other than black's auto-fix (e.g. a hook genuinely erroring rather than reformatting), stop and investigate before proceeding — do not skip or suppress the hook.

Re-run the same command until it exits 0 (auto-fixing hooks like black modify files in place, so a second run confirms nothing is left to fix):
```bash
.venv/bin/pre-commit run --all-files --show-diff-on-failure
```
Expected: exit code 0, no files modified on the second run.

- [ ] **Step 6: Run the test suite**

Run:
```bash
.venv/bin/pytest --cov=aiomodernforms --cov-report=xml -v
```
Expected: all tests pass under pytest 9.1.1 / pytest-asyncio 1.4.0 / pytest-cov 7.1.0. If any test fails due to a pytest-asyncio API change (e.g. deprecated fixture/marker usage), fix the failing test(s) in `tests/test_aiomodernforms.py` to use the current pytest-asyncio API — do not downgrade the dependency to make the failure disappear.

- [ ] **Step 7: Commit**

```bash
git add requirements_dev.txt requirements_test.txt .pre-commit-config.yaml aiomodernforms tests
git commit -m "Bump pip, black, wheel, pytest to close Dependabot alerts

Closes all pip (path traversal, command injection, tar/zip
confusion), black (arbitrary file write), and wheel (ReDoS) alerts,
plus the pytest tmpdir-handling alert. pytest-asyncio/pytest-cov are
bumped alongside pytest for compatibility."
```

---

### Task 2: Stage 2 — remaining dev-tooling refresh

**Files:**
- Modify: `requirements_dev.txt`
- Modify: `requirements_test.txt`
- Modify: `.pre-commit-config.yaml`

**Interfaces:** Consumes the files as left by Task 1 (black/pip/wheel/pytest/pytest-asyncio/pytest-cov already bumped, everything else still at Task 1's pinned versions). Produces the fully-refreshed dependency set with no further tasks depending on it.

- [ ] **Step 1: Update `requirements_dev.txt`**

Replace the full file contents with:

```
autopep8==2.0.4
black==26.5.1
blacken-docs==1.20.0
pip==26.1.2
pre-commit==4.6.1
twine==7.0.0
wheel==0.47.0
yamllint==1.38.0
```

- [ ] **Step 2: Update `requirements_test.txt`**

Replace the full file contents with:

```
aresponses==3.0.0
coverage==7.15.2
flake8==7.3.0
flake8-docstrings==1.7.0
isort==8.0.1
mypy==2.3.0
pylint==4.0.6
pytest==9.1.1
pytest-asyncio==1.4.0
pytest-cov==7.1.0
```

- [ ] **Step 3: Update `.pre-commit-config.yaml`**

Replace the full file contents with:

```yaml
---
repos:
  - repo: https://github.com/psf/black
    rev: 26.5.1
    hooks:
      - id: black
        args: [--safe, --quiet, --target-version, py311]
  - repo: https://github.com/adamchainz/blacken-docs
    rev: 1.20.0
    hooks:
      - id: blacken-docs
        additional_dependencies: [black==26.5.1]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-merge-conflict
      - id: debug-statements
      - id: check-docstring-first
      - id: check-json
      - id: check-yaml
      - id: requirements-txt-fixer
      - id: check-byte-order-marker
      - id: check-case-conflict
      - id: fix-encoding-pragma
        args: ["--remove"]
      - id: check-ast
      - id: detect-private-key
      - id: forbid-new-submodules
  - repo: https://github.com/pre-commit/pre-commit
    rev: v4.6.1
    hooks:
      - id: validate_manifest
  - repo: https://github.com/pre-commit/mirrors-autopep8
    rev: v2.0.4
    hooks:
      - id: autopep8
  - repo: https://github.com/PyCQA/isort
    rev: 8.0.1
    hooks:
      - id: isort
  - repo: https://github.com/pycqa/pylint
    rev: v4.0.6
    hooks:
      - id: pylint
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v2.3.0
    hooks:
      - id: mypy
  - repo: https://github.com/pycqa/flake8
    rev: 7.3.0
    hooks:
      - id: flake8
        additional_dependencies: ["flake8-docstrings"]
  - repo: https://github.com/adrienverge/yamllint.git
    rev: v1.38.0
    hooks:
      - id: yamllint
  - repo: https://github.com/asottile/pyupgrade
    rev: v3.21.2
    hooks:
      - id: pyupgrade
        args: [--py311-plus]
exclude: '^.github/.*'
```

Note: all currently-used hook `id`s (`check-byte-order-marker`, `fix-encoding-pragma`, `forbid-new-submodules`, etc.) were confirmed still present in `pre-commit-hooks` `v6.0.0` before writing this step — no hook renames/removals to account for.

- [ ] **Step 4: Reinstall dependencies into the existing venv**

Run:
```bash
.venv/bin/pip install -r requirements_dev.txt -r requirements_test.txt -r requirements.txt
```
Expected: pip installs/upgrades `isort`, `flake8`, `flake8-docstrings`, `pylint`, `mypy`, `autopep8`, `coverage`, `pre-commit`, `twine`, `blacken-docs`, `yamllint` with no errors.

- [ ] **Step 5: Run pre-commit across all files and resolve fallout**

Run:
```bash
.venv/bin/pre-commit run --all-files --show-diff-on-failure
```

This bump spans multiple major versions of isort (5→8), pylint (2→4), mypy (1→2), and flake8 (4→7), so genuinely new findings (not just auto-fixable formatting) are expected here, unlike Task 1. Handle failures by hook:

- `isort`, `autopep8`, other auto-fixing hooks: they modify files in place — re-run and confirm clean on the second pass, same as Task 1.
- `flake8`, `pylint`, `mypy`: these only report, they don't fix. For each reported error:
  - If it flags a real issue (e.g. a new deprecation warning, an actual type mismatch mypy 2.x now catches), fix the flagged code in `aiomodernforms/` or `tests/` directly.
  - If it's a false positive specific to the new tool version, do not blanket-disable the check repo-wide — add the narrowest possible inline suppression (e.g. `# pylint: disable=<specific-code>` or `# type: ignore[<specific-error>]`) directly on the flagged line, with a one-line comment explaining why it's a false positive.

Re-run until:
```bash
.venv/bin/pre-commit run --all-files --show-diff-on-failure
```
exits 0.

- [ ] **Step 6: Run the test suite**

Run:
```bash
.venv/bin/pytest --cov=aiomodernforms --cov-report=xml -v
```
Expected: all tests still pass (this stage doesn't touch pytest itself, but `coverage` and `pytest-cov` versions changed — confirm coverage reporting still works).

- [ ] **Step 7: Commit**

```bash
git add requirements_dev.txt requirements_test.txt .pre-commit-config.yaml aiomodernforms tests
git commit -m "Refresh remaining dev-tooling pins (isort, flake8, pylint, mypy, autopep8, pyupgrade, coverage, pre-commit, twine, blacken-docs, yamllint)

Brings the rest of the dev/lint toolchain up to current releases so
requirements_test.txt and .pre-commit-config.yaml stop drifting apart.
Not Dependabot-flagged, but stale enough to warrant syncing alongside
the security bump in the previous commit."
```

---

### Task 3: Verify against CI

**Files:** none modified — verification only.

**Interfaces:** Consumes the final state of `requirements_dev.txt`, `requirements_test.txt`, `.pre-commit-config.yaml`, `aiomodernforms/`, and `tests/` left by Task 2.

- [ ] **Step 1: Re-run the full local verification loop one more time from a clean install**

```bash
.venv/bin/pip install --upgrade -r requirements_dev.txt -r requirements_test.txt -r requirements.txt
.venv/bin/pre-commit run --all-files --show-diff-on-failure
.venv/bin/pytest --cov=aiomodernforms --cov-report=xml -v
```
Expected: pre-commit exits 0, all tests pass. This mirrors what `.github/workflows/ci.yml`'s `linting` and `test` jobs do, so a clean local run here means CI should pass too.

- [ ] **Step 2: Confirm no unintended files changed**

```bash
git status --short
git log --oneline -5
```
Expected: working tree clean (everything from Tasks 1–2 already committed), and the last two commits are the Stage 1 and Stage 2 commits from this plan.

- [ ] **Step 3: Push and open a PR (only if requested)**

Do not push or open a PR automatically — hand control back to the user to decide whether/when to push, per this project's standing rule of confirming before any action visible to others.

---

## Self-Review Notes

- **Spec coverage:** every package in the spec's three version tables is bumped somewhere in Task 1 or Task 2; the `.pre-commit-config.yaml` sync, target-version/`--py311-plus` changes, staged-commit structure, and verification commands from the spec are all represented.
- **Placeholder scan:** no TBD/TODO; every step has literal file contents or literal commands.
- **Type/name consistency:** N/A (no new functions/interfaces introduced by this plan — it's a dependency/config bump).
- **Known deviation:** `autopep8` target lowered from the spec's `2.3.2` to `2.0.4` because the pre-commit mirror repo caps there — documented in Global Constraints above.
