import re
from dataclasses import dataclass, field


class DiffParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NewFileLine:
    path: str
    line: int
    content: str
    added: bool
    hunk: int


@dataclass(slots=True)
class FileDiff:
    path: str
    raw: str
    lines: list[NewFileLine] = field(default_factory=list)

    @property
    def byte_size(self) -> int:
        return len(self.raw.encode("utf-8"))

    @property
    def added_lines(self) -> list[NewFileLine]:
        return [line for line in self.lines if line.added]


HUNK_RE = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@")


def _clean_path(header: str) -> str:
    value = header.rstrip("\r\n").split("\t", 1)[0].strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    return value


def _section_starts(lines: list[str]) -> list[int]:
    git_starts = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    if git_starts:
        return git_starts
    return [
        index
        for index in range(len(lines) - 1)
        if lines[index].startswith("--- ") and lines[index + 1].startswith("+++ ")
    ]


def parse_unified_diff(diff: str) -> list[FileDiff]:
    if not diff or not diff.strip():
        raise DiffParseError("Diff is empty.")

    source_lines = diff.splitlines(keepends=True)
    starts = _section_starts(source_lines)
    if not starts:
        raise DiffParseError("No unified-diff file header was found.")

    sections: list[list[str]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(source_lines)
        sections.append(source_lines[start:end])

    parsed: list[FileDiff] = []
    saw_hunk = False
    for section in sections:
        new_header_index = next(
            (index for index, line in enumerate(section) if line.startswith("+++ ")),
            None,
        )
        old_header_exists = any(line.startswith("--- ") for line in section)
        if new_header_index is None or not old_header_exists:
            raise DiffParseError("A file section is missing ---/+++ headers.")

        path = _clean_path(section[new_header_index][4:])
        if not path:
            raise DiffParseError("A file path is empty.")
        file_diff = FileDiff(path=path, raw="".join(section))

        current_new_line: int | None = None
        hunk_number = -1
        for line in section[new_header_index + 1 :]:
            hunk_match = HUNK_RE.match(line)
            if hunk_match:
                current_new_line = int(hunk_match.group(1))
                hunk_number += 1
                saw_hunk = True
                continue
            if current_new_line is None:
                continue
            if line.startswith("\\ No newline at end of file"):
                continue
            content = line[1:].rstrip("\r\n") if line else ""
            if line.startswith("+") and not line.startswith("+++"):
                if path != "/dev/null":
                    file_diff.lines.append(
                        NewFileLine(path, current_new_line, content, True, hunk_number)
                    )
                current_new_line += 1
            elif line.startswith(" "):
                if path != "/dev/null":
                    file_diff.lines.append(
                        NewFileLine(path, current_new_line, content, False, hunk_number)
                    )
                current_new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                continue
            else:
                current_new_line = None

        parsed.append(file_diff)

    if not saw_hunk:
        raise DiffParseError("The diff contains no valid hunks.")
    return parsed
