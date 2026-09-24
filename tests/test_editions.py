"""Edition guard + mint matrix (story 1.7 / AD-5, NFR5).

Covers the ``check_editions.py`` matrix on staged git repos:
EDITION_ABSENT / empty (zero-edition state), EDITION_GRAMMAR,
EDITION_OVERWRITE (modify and delete against the base ref, via the
``BASE_REF`` env), renames (into an existing edition fail; entirely
outside editions pass), EDITION_NEW (a new grammar-conforming edition
dir passes), and NO_GIT / NO_BASE (structural pass, mirroring gate 5's
cold-start). Also the ``mint_edition.py`` refusals (usage, invalid id,
no built dist, MINT_EXISTS) and the happy-path mint with the
edition-recursion exclusion. Reuses the stage_minimal-style harness
pattern: bare repo-shaped tmp roots + git plumbing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK = REPO_ROOT / "scripts" / "check_editions.py"


def run_check(
    root: Path, base_ref: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run check_editions.py [root] with BASE_REF controlled (env inherited
    otherwise stripped, so a developer's ambient BASE_REF cannot leak in)."""
    env = {k: v for k, v in os.environ.items() if k != "BASE_REF"}
    if base_ref is not None:
        env["BASE_REF"] = base_ref
    return subprocess.run(
        [sys.executable, str(CHECK), str(root)],
        capture_output=True,
        text=True,
        check=False,  # intentional: exit codes are asserted per test
        env=env,
    )


def run_mint(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run mint_edition.py with its REPO_ROOT resolved to ``root``.

    Same pattern as run_cli_zero_args: the script is copied under
    ``root/scripts/`` so its ``REPO_ROOT`` (``Path(__file__).resolve().
    parent.parent``) resolves to the staged root, not the real repo.
    """
    target = root / "scripts" / "mint_edition.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "scripts" / "mint_edition.py", target)
    return subprocess.run(
        [sys.executable, str(target), *args],
        capture_output=True,
        text=True,
        check=False,  # intentional: exit codes are asserted per test
    )


def git_run(root: Path, *args: str) -> None:
    # -c identity: commits must work on machines without a global git id.
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=editions-test",
            "-c",
            "user.email=editions-test@example.com",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def commit_all(root: Path, message: str = "seed") -> str:
    git_run(root, "add", "-A")
    git_run(root, "commit", "-q", "-m", message)
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def stage_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git_run(root, "init", "-q")
    return root


def write_edition_file(root: Path, edition: str, name: str, body: str) -> Path:
    path = root / "web" / "editions" / edition / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def stage_mint_root(tmp_path: Path) -> Path:
    """A repo-shaped root with a built web/dist (including a recursion trap)."""
    root = tmp_path / "repo"
    dist = root / "web" / "dist"
    (dist / "figures").mkdir(parents=True)
    (dist / "index.html").write_text("<html>latest</html>\n", encoding="utf-8")
    (dist / "figures" / "page.html").write_text("x", encoding="utf-8")
    # The recursion trap: an editions/ dir inside dist must never survive
    # the mint copy.
    (dist / "editions").mkdir()
    (dist / "editions" / "inner.html").write_text("trap", encoding="utf-8")
    return root


# ---------------------------------------------------------------- usage


def test_check_usage_and_bad_root(tmp_path: Path) -> None:
    too_many = subprocess.run(
        [sys.executable, str(CHECK), "a", "b"],
        capture_output=True,
        text=True,
        check=False,  # intentional: exit code is asserted
    )
    assert too_many.returncode == 2
    assert "usage:" in too_many.stderr
    bad_root = run_check(tmp_path / "does-not-exist")
    assert bad_root.returncode == 2
    assert "no such directory" in bad_root.stderr


# ---------------------------------------------------------------- zero-edition state


def test_editions_absent_is_structural_pass(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    result = run_check(root)
    assert result.returncode == 0, result.stderr
    assert "OK: editions" in result.stdout
    assert "zero-edition" in result.stdout


def test_editions_empty_dir_passes(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    (root / "web" / "editions").mkdir(parents=True)
    result = run_check(root)
    assert result.returncode == 0, result.stderr
    assert "zero-edition" in result.stdout


# ---------------------------------------------------------------- grammar


def test_grammar_violation_fails_naming_dir(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    (root / "web" / "editions" / "26x").mkdir(parents=True)
    result = run_check(root)
    assert result.returncode == 1
    assert "web/editions/26x" in result.stderr


def test_grammar_allows_valid_forms(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    (root / "web" / "editions" / "2026").mkdir(parents=True)
    (root / "web" / "editions" / "2026-1").mkdir()
    result = run_check(root)
    assert result.returncode == 0, result.stderr
    assert "2 grammar-conforming" in result.stdout


def test_grammar_file_entry_fails(tmp_path: Path) -> None:
    # A plain FILE named like an edition is not a grammar-conforming dir.
    root = stage_repo(tmp_path)
    (root / "web" / "editions").mkdir(parents=True)
    (root / "web" / "editions" / "latest").write_text("x", encoding="utf-8")
    result = run_check(root)
    assert result.returncode == 1
    assert "web/editions/latest" in result.stderr


# ---------------------------------------------------------------- no-git / no-base


def test_no_git_with_valid_editions_is_structural_pass(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "x")
    # Even with a BASE_REF set, no .git tree -> the diff guard is skipped.
    result = run_check(root, base_ref="abc123")
    assert result.returncode == 0, result.stderr
    assert "skipped" in result.stdout


def test_no_base_ref_skips_diff_guard(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "old")
    commit_all(root)
    # A dirty (uncommitted) modification must not fail without a base ref.
    write_edition_file(root, "2026", "index.html", "new")
    result = run_check(root)
    assert result.returncode == 0, result.stderr
    assert "no BASE_REF env" in result.stdout


def test_unobtainable_base_ref_is_structural_pass(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "x")
    commit_all(root)
    result = run_check(root, base_ref="no-such-ref")
    assert result.returncode == 0, result.stderr
    assert "not obtainable" in result.stdout


# ---------------------------------------------------------------- no-overwrite


def test_overwrite_modify_fails_naming_path(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "old")
    base_sha = commit_all(root, "seed")
    write_edition_file(root, "2026", "index.html", "new")
    commit_all(root, "modify an edition")
    result = run_check(root, base_ref=base_sha)
    assert result.returncode == 1
    assert "web/editions/2026/index.html" in result.stderr
    assert "FAIL: editions" in result.stderr


def test_overwrite_delete_fails_naming_path(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    path = write_edition_file(root, "2026", "figure.html", "x")
    base_sha = commit_all(root, "seed")
    path.unlink()
    commit_all(root, "delete an edition file")
    result = run_check(root, base_ref=base_sha)
    assert result.returncode == 1
    assert "web/editions/2026/figure.html" in result.stderr
    assert "modified or deleted" in result.stderr


def test_append_under_existing_edition_fails(tmp_path: Path) -> None:
    # NFR5 immutability: an edition tree is frozen once it exists at the
    # base ref; even an append inside it is a modification.
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "x")
    base_sha = commit_all(root, "seed")
    write_edition_file(root, "2026", "extra.html", "y")
    commit_all(root, "append to an edition")
    result = run_check(root, base_ref=base_sha)
    assert result.returncode == 1
    assert "web/editions/2026/extra.html" in result.stderr


def test_new_edition_dir_passes(tmp_path: Path) -> None:
    # EDITION_NEW: creation of a new grammar-conforming edition dir is the
    # only allowed change under web/editions.
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "x")
    base_sha = commit_all(root, "seed")
    write_edition_file(root, "2027", "index.html", "new edition")
    commit_all(root, "mint 2027")
    result = run_check(root, base_ref=base_sha)
    assert result.returncode == 0, result.stderr
    assert "no path under an existing edition changed" in result.stdout


def test_rename_into_existing_edition_fails(tmp_path: Path) -> None:
    # A rename from outside web/editions/ into an edition that exists at
    # the base ref appends to a frozen tree; the destination is judged,
    # not just the diff's source path.
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "x")
    (root / "web" / "doc.html").write_text("movable content", encoding="utf-8")
    base_sha = commit_all(root, "seed")
    git_run(
        root,
        "mv",
        "web/doc.html",
        "web/editions/2026/renamed.html",
    )
    commit_all(root, "rename a doc into an edition")
    result = run_check(root, base_ref=base_sha)
    assert result.returncode == 1
    assert "web/editions/2026/renamed.html" in result.stderr
    assert "FAIL: editions" in result.stderr


def test_rename_outside_editions_passes(tmp_path: Path) -> None:
    # A rename that never touches web/editions/ is out of the guard's
    # jurisdiction even when an existing edition sits at the base ref.
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "x")
    (root / "web" / "doc.html").write_text("movable content", encoding="utf-8")
    base_sha = commit_all(root, "seed")
    git_run(root, "mv", "web/doc.html", "web/other.html")
    commit_all(root, "rename outside editions")
    result = run_check(root, base_ref=base_sha)
    assert result.returncode == 0, result.stderr
    assert "no path under an existing edition changed" in result.stdout


def test_changes_outside_editions_pass(tmp_path: Path) -> None:
    # The guard is scoped to web/editions: changes elsewhere are out of
    # its jurisdiction.
    root = stage_repo(tmp_path)
    write_edition_file(root, "2026", "index.html", "x")
    (root / "README.md").write_text("doc", encoding="utf-8")
    base_sha = commit_all(root, "seed")
    (root / "README.md").write_text("doc v2", encoding="utf-8")
    commit_all(root, "touch a doc")
    result = run_check(root, base_ref=base_sha)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------- mint


def test_mint_usage_exit_two(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    no_args = run_mint(root)
    assert no_args.returncode == 2
    assert "usage:" in no_args.stderr
    too_many = run_mint(root, "2026", "extra")
    assert too_many.returncode == 2
    assert "usage:" in too_many.stderr


def test_mint_invalid_id_refuses(tmp_path: Path) -> None:
    root = stage_mint_root(tmp_path)
    for bad_id in ("26", "2026x", "2026-1-2", ""):
        result = run_mint(root, bad_id)
        assert result.returncode == 1, (bad_id, result.stderr)
        assert "not grammar-conforming" in result.stderr


def test_mint_without_built_dist_refuses(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    result = run_mint(root, "2026")
    assert result.returncode == 1
    assert "no built" in result.stderr
    assert "web/dist" in result.stderr
    assert not (root / "web" / "editions").exists()


def test_mint_exists_refuses_and_writes_nothing(tmp_path: Path) -> None:
    # MINT_EXISTS: an existing edition dir is frozen; nothing is written.
    root = stage_mint_root(tmp_path)
    existing = write_edition_file(root, "2026", "index.html", "frozen")
    before = existing.read_bytes()
    result = run_mint(root, "2026")
    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert existing.read_bytes() == before
    assert list((root / "web" / "editions" / "2026").iterdir()) == [existing]


def test_mint_happy_path_copies_dist_minus_editions(tmp_path: Path) -> None:
    root = stage_mint_root(tmp_path)
    result = run_mint(root, "2026")
    assert result.returncode == 0, result.stderr
    target = root / "web" / "editions" / "2026"
    assert (target / "index.html").is_file()
    assert (target / "figures" / "page.html").is_file()
    # The recursion trap did not survive the mint copy.
    assert not (target / "editions").exists()
