# Agentic OS v0.2 — U-P1 packaging contract

Task: T-0010 — `python -m agentic_os` + zipapp `aos.pyz` build
Branch: `v0.2-u-p1-packaging`
Baseline: `9029f0bed42c3748214e01f82e7cd38b7df2a5e0`

This contract pins behavior **before** production changes. Packaging is
additive: it adds ways to *reach* the CLI. It does not change what the CLI
*does*.

---

## 1. Scope

In scope: a module entrypoint, an installable console-script declaration, a
stdlib-only zipapp builder, docs, and regression tests.

Out of scope (explicitly not done in this pass): CI, release publishing,
branch protection, Docker, migrations, third-party runtime libraries, global
installation, commits/pushes/tags, and any change to ledger semantics.

---

## 2. Canonical CLI (D-U-P1-01)

There is exactly **one** canonical CLI implementation:

```
agentic_os.cli.main(argv: list[str] | None = None) -> int
```

`main()` owns the argparse tree, command dispatch, exit-code mapping, and
exception handling. Every entrypoint is a thin shim that calls it and exits
with its return value:

```python
sys.exit(main())
```

Three entrypoints, one implementation:

| Entrypoint            | File                     | Shim body            |
| --------------------- | ------------------------ | -------------------- |
| `python3 aos.py`      | `aos.py` (exists)        | `sys.exit(main())`   |
| `python3 -m agentic_os` | `agentic_os/__main__.py` | `sys.exit(main())` |
| `python3 aos.pyz`     | archive `__main__.py`    | `sys.exit(main())`   |

No entrypoint may duplicate the argparse tree or dispatch. `aos.py` is
already a thin shim at baseline, so **`aos.py` is not modified**.

**Verified at baseline, load-bearing:** `build_parser()` pins `prog="aos"`
(`agentic_os/cli.py:935`). Help/usage text is therefore derived from the
pinned prog, not from `sys.argv[0]`, so `--help` output is byte-identical
across all three entrypoints *by construction*. No `cli.py` change is
required to make help match. **`agentic_os/cli.py` is not modified.**

### 2.1 Archive entrypoint identity (D-U-P1-02)

The zipapp's top-level `__main__.py` is a **byte-for-byte copy** of
`agentic_os/__main__.py`, placed at the archive root by the builder.

Rationale: this makes "all entrypoints share one canonical CLI" mechanically
true rather than a convention maintained by hand — there is no third copy of
the shim to drift. It requires `agentic_os/__main__.py` to use the absolute
import `from agentic_os.cli import main` (not a relative `from .cli import`),
so the same file is valid both inside the package (under `-m`) and at the
archive root. A test asserts the byte-identity.

`zipapp.create_archive(main=...)` is **not** used: its generated stub calls
`fn()` and discards the return value, which would force exit code 0 for every
command. That would break exit-code equivalence, so the shim is explicit.

---

## 3. Zero runtime dependencies (D-U-P1-03)

`aos.pyz` runs on stock Python 3.12 with **nothing** outside the standard
library. `pyproject.toml` declares `dependencies = []`. Build-system
requirements (`setuptools`) are build-time only and are not runtime
dependencies. The builder itself is stdlib-only (`zipapp`, `pathlib`,
`shutil`, `tempfile`, `os`, `stat`, `argparse`, `sys`).

---

## 4. Packaging metadata

`pyproject.toml`:

- name `agentic-os`; version is `dynamic`, read from `agentic_os.__version__`
  (single source of truth — no duplicated version literal);
- `requires-python = ">=3.12"`;
- `dependencies = []`;
- `[project.scripts] aos = "agentic_os.cli:main"` — the console script
  delegates to the canonical CLI;
- `[tool.setuptools] packages = ["agentic_os"]` — an explicit allowlist, not
  auto-discovery, so tests, ledger data, backups, exports, caches, and
  repository-only files can never be swept in.

Not installed or published in this pass.

---

## 5. Builder (`tools/build_zipapp.py`)

```
python3 tools/build_zipapp.py
python3 tools/build_zipapp.py --output PATH
```

Default output: `dist/aos.pyz`.

### 5.1 Membership — allowlist (D-U-P1-04)

The archive contains **only**:

- `agentic_os/**/*.py` — files under the package whose suffix is exactly
  `.py`, excluding any path with a `__pycache__` component;
- a top-level `__main__.py` (the copy from §2.1).

This is an **allowlist by construction**, not a denylist of bad names. Every
required exclusion (`.git`, `.agentic-os`, `tests/`, `__pycache__`, `*.pyc`,
`*.db`, backups, exports, local settings, credentials, `*.md` doc trees,
`adapters/`, `research/`, `aos_hooks.py`, and any unrelated repository file)
follows from the allowlist: those are either not under `agentic_os/`, or not
`.py`, or under `__pycache__`. A denylist can be defeated by a new file with
an unanticipated name; an allowlist cannot.

Entries are added in sorted order for a deterministic archive.

### 5.2 Output-path safety (D-U-P1-05)

The output path is inspected with `os.lstat` (**not** `stat`, so a symlink is
seen as a symlink rather than followed to its target). If the path exists and
is **not a regular file**, the build refuses:

- symlink (even one pointing at a regular file) → refuse
- directory, FIFO, socket, block/char device, or any other non-regular object
  → refuse

Refusal is fail-closed: exit nonzero, one concise diagnostic, **the existing
object is not touched, replaced, or removed**. An existing *regular* file is a
legal destination and is replaced only on success (§5.3).

The output parent is created when safe (`mkdir(parents=True, exist_ok=True)`);
an `OSError` there (e.g. parent exists as a file) is a concise diagnostic and
a nonzero exit.

### 5.3 Atomic replacement (D-U-P1-06)

1. staging tree built in a `TemporaryDirectory` outside the source tree;
2. archive written to a temporary file **in the destination's parent
   directory** (same filesystem, so the final rename is atomic);
3. `chmod 0o755` on the temp archive;
4. `os.replace(tmp, output)` — the destination is replaced only after a
   complete, successful build.

Therefore:

- a failure at any earlier step leaves **no partial final archive** — the
  destination is never opened for writing until the rename;
- an existing valid destination survives a failed rebuild **byte-identically**;
- the temp archive is removed in a `finally` block, so no debris remains.

### 5.4 Failure behavior (D-U-P1-07)

Builder errors exit nonzero with one concise diagnostic on stderr. Diagnostics
name paths and conditions only — they never print file contents or secrets.

### 5.5 Source-tree safety

The builder does not modify the source tree except for the requested output
artifact (and its short-lived sibling temp file in the destination directory).

---

## 6. Executable archive

`zipapp.create_archive(..., interpreter="/usr/bin/env python3")` writes the
shebang `#!/usr/bin/env python3`. The builder additionally sets mode `0o755`
explicitly rather than relying on zipapp's owner-execute-only bit, so the
artifact is predictably executable.

---

## 7. Runtime equivalence (D-U-P1-08)

Same parser, same behavior:

- `python3 aos.py --help`
- `python3 -m agentic_os --help`
- `python3 dist/aos.pyz --help`

must produce identical stdout and identical exit codes.

In disposable workspaces, the module and zipapp entrypoints must succeed at
`init`, `status`, and `doctor`.

**Verified at baseline:** root resolution is `--root PATH` (explicit) or
cwd-upward discovery from `Path.cwd()` (`agentic_os/utils.py:116`). It never
consults `__file__` or `sys.argv[0]`. The archive therefore works from any
directory, from outside the repository, with `PYTHONPATH` cleared and the
repository absent from `sys.path`.

**Verified at baseline:** a fresh `init` yields `doctor` → 20 checks PASS,
exit 0. `doctor` reads only the workspace and never touches the entrypoint's
location, so it passes identically from the archive.

---

## 8. Root and data safety (D-U-P1-09)

Packaging changes nothing about: database schema, CLI commands or flags, hook
behavior, dropfile behavior, evidence rules, backup/export behavior, doctor
semantics, migration behavior, or AICompany.

No user ledger, `.agentic-os` workspace, generated vault, backup, or credential
may be embedded in the archive — guaranteed by the §5.1 allowlist.

---

## 9. Generated artifacts are not committed (D-U-P1-10)

`dist/` and `*.pyz` are gitignored. The archive is a build output, reproducible
from source; committing it would create a second, silently-stale copy of the
runtime.

---

## 10. Known limitation — `hooks install` from the archive (D-U-P1-11)

`agentic_os/hooks.py:758` `default_runner_path()` resolves the hook runner as
`Path(__file__).resolve().parent.parent / "aos_hooks.py"` — i.e. the
`aos_hooks.py` that ships **beside `aos.py` in a checkout**. Inside a zipapp,
`__file__` is a path *within* the archive, so that resolves to
`<...>/aos.pyz/aos_hooks.py`, which does not exist. There is no `--runner`
override flag on `hooks install`.

Consequence: `hooks install` / `hooks status` / `hooks uninstall` are **not
supported from `aos.pyz`**; use a source checkout for hook management. This is
a documented limitation, **not fixed here**:

- `aos_hooks.py` is not part of the `agentic_os` runtime package, so shipping
  it would violate the §5.1 allowlist and D-U-P1 "runtime package only";
- a Claude settings hook must point at a stable on-disk script path, which a
  zipapp's interior path is not;
- fixing it means changing `hooks.py`, which this task forbids absent an
  actual incompatibility blocking a shared entrypoint. This blocks *one
  command from one entrypoint*; it does not block the shared entrypoint.

`init`, `status`, and `doctor` — the required archive paths — do not call
`default_runner_path()`; it is reached only from the hooks install/status/
uninstall handlers. The required paths are unaffected.

---

## 11. Regression tests (`tests/test_v02_packaging.py`)

Tests exercise the production branch and inspect real filesystem state; they
do not assert on generic error wording.

1. `python -m agentic_os` delegates to the canonical CLI.
2. Module and script `--help` stdout and exit codes match.
3. Builder creates a valid executable zipapp.
4. Zipapp `--help` succeeds outside the repository with `PYTHONPATH` removed.
5. Zipapp `init` succeeds in a new disposable workspace.
6. Zipapp `status` succeeds after init.
7. Zipapp `doctor` reports all checks passing after init.
8. Module entrypoint runs init/status/doctor in a disposable workspace.
9. Archive membership contains only required runtime files.
10. Archive contains no tests, `.git`, `.agentic-os`, pycache, `.pyc`, DB,
    backup, export, credential, or local-settings files.
11. Existing destination survives an injected build failure byte-identically.
12. No partial destination appears when the first build fails.
13. Existing symlink, directory, FIFO, and other unsafe output objects refuse
    without replacement.
14. Custom output path works.
15. Console-script metadata points to the canonical CLI.
16. `pyproject` declares no runtime dependencies.
17. Existing `aos.py` behavior remains unchanged.
