"""Estimate authored-source byte ratios without changing GitHub Linguist rules."""

from collections import Counter
from pathlib import Path
import os
import subprocess


LANGUAGES = {
    ".py": "Python",
    ".css": "CSS",
    ".html": "HTML",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".sh": "Shell",
}


def source_files(root: Path) -> list[Path]:
    """Include tracked and new files, respecting Git's existing ignore rules."""
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
    )
    candidates = {root / os.fsdecode(name) for name in output.split(b"\0") if name}
    return sorted(
        path for path in candidates
        if path.suffix.lower() in LANGUAGES and path.is_file() and not path.is_symlink()
    )


def is_test(path: Path) -> bool:
    """Recognize the repository's Python and browser test file conventions."""
    return (
        bool({"test", "tests", "__tests__"}.intersection(path.parts))
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or ".test." in path.name
        or ".spec." in path.name
    )


def report(label: str, paths: list[Path]) -> bool:
    counts: Counter[str] = Counter()
    for path in paths:
        counts[LANGUAGES[path.suffix.lower()]] += path.stat().st_size
    total = sum(counts.values())
    print(f"\n{label}: {total:,} source bytes")
    for language, size in counts.most_common():
        print(f"  {language:12} {size:>9,} bytes  {size / total:>6.2%}")
    passed = total > 0 and counts["Python"] * 2 > total
    print(f"  Python > 50%: {'PASS' if passed else 'FAIL'}")
    return passed


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    paths = source_files(root)
    print("Local estimate; GitHub Languages uses its own Linguist classification.")
    print("Counts known source extensions; excludes ignored files and missing files.")
    all_passed = report("All authored sources (including tests)", paths)
    production_passed = report(
        "Sources excluding tests", [path for path in paths if not is_test(path.relative_to(root))]
    )
    return 0 if all_passed and production_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
