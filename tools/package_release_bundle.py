#!/usr/bin/env python3
"""Build a fresh CLI/documentation folder without executing the supplied binary.

Only the explicit release inputs below are traversed. This is a documentation
layout check, not a build, runtime test, or source-command reproducibility claim.
Source inputs must remain unchanged while packaging; symlinks are not accepted.
Link checks cover inline Markdown links/images, reference definitions, and HTML
img/src and a/href targets, skipping fenced/inline code and external URLs. They
check bundled path existence, not fragment anchors or complete CommonMark syntax.
"""
import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
import ntpath
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "README.md", "LICENSE", "CHANGELOG.md", "CITATION.cff",
    "validation/README.md", "plugins/packages/MVS_Report_Pack_v1.0.0.mvsplugin",
    "plugins/packages/example-visualization.mvsplugin",
)
REQUIRED_TREES = (
    "docs", "examples", "notebooks", "benchmark_history",
    "plugins/sources/plugin-example-source", "plugins/sources/plugin-report-pack-source",
    "plugins/sources/plugin-lab-pack-source", "plugins/sources/plugin-stress-pack-source",
)


class BundleError(ValueError):
    """A missing or unsafe release input; no existing output is replaced."""


@dataclass(frozen=True)
class BundleResult:
    files: int
    markdown_files: int
    local_links: int


def _no_symlink_components(path):
    """Check parents as well as the leaf, including dangling symbolic links."""
    for component in reversed((path, *path.parents)):
        if component.is_symlink():
            raise BundleError(f"Symlink input/output component is not allowed: {component}")


def _absolute(path):
    path = Path(path).absolute()
    # Check before resolve: resolving first would hide a parent/leaf alias.
    _no_symlink_components(path)
    return path.resolve()


def _kind(path):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise BundleError(f"Missing required source entry: {path}") from exc
    if stat.S_ISLNK(mode):
        raise BundleError(f"Symlink source entry is not allowed: {path}")
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    raise BundleError(f"Source entry is not a regular file or directory: {path}")


class _HtmlLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        key = "src" if tag == "img" else "href" if tag == "a" else None
        target = dict(attrs).get(key)
        if target:
            self.links.append(target)


def _prose(text):
    """Ignore fenced and inline code, which are examples rather than links."""
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence):
                fence = None
            lines.append("\n")
        elif match:
            fence = match[1]
            lines.append("\n")
        else:
            lines.append(line)
    return re.sub(r"(`+)(?!`)(.*?)\1(?!`)", "", "".join(lines), flags=re.DOTALL)


def _markdown_links(text):
    """Read inline links/images, reference destinations, and HTML img/a tags.

    Inline destinations support angle brackets, escaped punctuation, titles,
    and balanced parentheses. Reference definitions are checked even if unused.
    """
    text = _prose(text)
    html = _HtmlLinks()
    html.feed(text)
    yield from html.links
    for match in re.finditer(r"(?<!\\)\]\(\s*", text):
        start = match.end()
        if start < len(text) and text[start] == "<":
            end = text.find(">", start + 1)
            if end != -1:
                yield text[start + 1:end]
            continue
        end, depth = start, 0
        while end < len(text):
            char = text[end]
            if char == "\\" and end + 1 < len(text):
                end += 2
                continue
            if char.isspace() or (char == ")" and depth == 0):
                break
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            end += 1
        if end > start:
            yield re.sub(r"\\([^\w\s])", r"\1", text[start:end])
    for match in re.finditer(r"(?m)^ {0,3}\[[^\]\n]+\]:\s*(?:<([^>\n]+)>|(\S+))", text):
        yield re.sub(r"\\([^\w\s])", r"\1", match[1] or match[2])


def _local_target(document, link):
    try:
        parsed = urlsplit(link)
    except ValueError as exc:
        raise BundleError(f"Invalid link in {document}: {link}") from exc
    if parsed.netloc and parsed.scheme.lower() != "file":
        return None
    if parsed.scheme.lower() == "file" or ntpath.splitdrive(link)[0]:
        raise BundleError(f"Unsafe local link in {document}: {link}")
    if parsed.scheme or not parsed.path:
        return None
    path = unquote(parsed.path)
    if "\\" in path or "\x00" in path or path.startswith("/") or ntpath.splitdrive(path)[0]:
        raise BundleError(f"Unsafe local link in {document}: {link}")
    parts = list(document.parent.parts)
    for part in PurePosixPath(path).parts:
        if part == "..":
            if not parts:
                raise BundleError(f"Local link escapes bundle in {document}: {link}")
            parts.pop()
        elif part != ".":
            parts.append(part)
    return PurePosixPath(*parts)


def create_bundle(root, cli, out):
    """Preflight all inputs/links, then copy into a new folder; never delete it."""
    root, cli, out = (_absolute(path) for path in (root, cli, out))
    if not root.is_dir():
        raise BundleError(f"Source root is not a directory: {root}")
    if _kind(cli) != "file":
        raise BundleError(f"CLI must be a regular file: {cli}")
    if out.exists():
        raise BundleError(f"Output already exists; choose a fresh directory: {out}")
    for parent in out.parents:
        if parent.exists() and not parent.is_dir():
            raise BundleError(f"Output parent is not a directory: {parent}")
    for source in [cli, *(root / name for name in REQUIRED_FILES + REQUIRED_TREES)]:
        if source.is_relative_to(out) or out == source:
            raise BundleError(f"Output overlaps source input: {source}")
    for name in REQUIRED_TREES:
        if out.is_relative_to(root / name):
            raise BundleError(f"Output is inside a selected source tree: {name}")

    files = {PurePosixPath("mvs"): cli}
    directories = {PurePosixPath(".")}

    def collect(relative, expected=None):
        source = root.joinpath(*relative.parts)
        _no_symlink_components(source)
        kind = _kind(source)
        if expected and kind != expected:
            raise BundleError(f"Expected source {expected}: {source}")
        if kind == "directory":
            # Only Python's machine-local cache directories are omitted. A file
            # with this name, and every other source asset, must be preserved.
            if relative.name == "__pycache__":
                return
            directories.add(relative)
            for child in sorted(source.iterdir(), key=lambda item: item.name):
                collect(relative / child.name)
        else:
            files[relative] = source
            directories.update(relative.parents)

    for name in REQUIRED_FILES:
        collect(PurePosixPath(name), "file")
    for name in REQUIRED_TREES:
        collect(PurePosixPath(name), "directory")

    markdown_count = link_count = 0
    available = files.keys() | directories
    for relative, source in files.items():
        if relative.suffix.lower() != ".md":
            continue
        markdown_count += 1
        for link in _markdown_links(source.read_text(encoding="utf-8-sig")):
            target = _local_target(relative, link)
            if target is not None:
                if target not in available:
                    raise BundleError(f"Missing bundled link target in {relative}: {link}")
                link_count += 1

    # No output or parent directory is created until every preflight has passed.
    out.mkdir(parents=True, exist_ok=False)
    for relative in sorted(directories, key=lambda path: (len(path.parts), str(path))):
        if relative.parts:
            out.joinpath(*relative.parts).mkdir(exist_ok=False)
    for relative, source in files.items():
        _no_symlink_components(source)
        if _kind(source) != "file":
            raise BundleError(f"Source changed during packaging: {source}")
        shutil.copy2(source, out.joinpath(*relative.parts))
    return BundleResult(len(files), markdown_count, link_count)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="source root (default: repository)")
    parser.add_argument("--cli", type=Path, required=True, help="already-built CLI file to copy as mvs")
    parser.add_argument("--out", type=Path, required=True, help="new bundle directory; must not exist")
    args = parser.parse_args(argv)
    try:
        result = create_bundle(args.root, args.cli, args.out)
    except (BundleError, OSError, UnicodeError) as exc:
        parser.exit(1, f"Release bundle failed: {exc}\n")
    print(f"Release bundle layout: {result.files} files, {result.markdown_files} Markdown files, "
          f"{result.local_links} local links verified.")
    print("CLI copied without execution; this is not build or runtime validation.")


if __name__ == "__main__":
    main()
