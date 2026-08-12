import re
from dataclasses import dataclass
from typing import Literal

from app.diff.chunker import ReviewChunk
from app.diff.parser import FileDiff, NewFileLine
from app.schemas import Finding


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    severity: Literal["critical", "high", "medium", "low"]
    category: Literal["security", "correctness", "performance", "style"]
    title: str
    pattern: re.Pattern[str]


RULES = (
    Rule("MOCK-001", "critical", "security", "eval usage", re.compile(r"eval\(")),
    Rule(
        "MOCK-002",
        "critical",
        "security",
        "hardcoded credential",
        re.compile(
            r"(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "MOCK-003",
        "high",
        "security",
        "SQL string concatenation",
        re.compile(
            r"(?:['\"][^'\"]*\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^'\"]*['\"]\s*\+|"
            r"\+\s*['\"][^'\"]*\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^'\"]*['\"])",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "MOCK-005",
        "medium",
        "correctness",
        "loose null comparison",
        re.compile(r"(?:==|!=)\s*null"),
    ),
    Rule(
        "MOCK-006",
        "medium",
        "performance",
        "deep-clone via JSON",
        re.compile(r"JSON\.parse\(JSON\.stringify\("),
    ),
    Rule("MOCK-007", "low", "style", "console.log left in", re.compile(r"console\.log\(")),
    Rule("MOCK-008", "low", "style", "unresolved marker", re.compile(r"TODO|FIXME")),
    Rule(
        "MOCK-INJ",
        "critical",
        "security",
        "prompt-injection content",
        re.compile(
            r"ignore previous instructions|disregard all prior|you are now",
            re.IGNORECASE,
        ),
    ),
)


def _finding(rule: Rule, line: NewFileLine) -> Finding:
    return Finding(
        id=f"{rule.rule_id}:{line.path}:{line.line}",
        ruleId=rule.rule_id,
        path=line.path,
        line=line.line,
        severity=rule.severity,
        category=rule.category,
        title=rule.title,
        evidence=line.content,
    )


def _empty_catch_lines(file_diff: FileDiff) -> list[NewFileLine]:
    findings: list[NewFileLine] = []
    catch_pattern = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{")
    by_hunk: dict[int, list[NewFileLine]] = {}
    for line in file_diff.lines:
        by_hunk.setdefault(line.hunk, []).append(line)

    for hunk_lines in by_hunk.values():
        for index, catch_line in enumerate(hunk_lines):
            if not catch_line.added:
                continue
            match = catch_pattern.search(catch_line.content)
            if match is None:
                continue
            depth = 1
            body_parts: list[str] = []
            candidates = [catch_line.content[match.end() :]] + [
                line.content for line in hunk_lines[index + 1 :]
            ]
            closed = False
            for candidate in candidates:
                for character in candidate:
                    if character == "{":
                        depth += 1
                        body_parts.append(character)
                    elif character == "}":
                        depth -= 1
                        if depth == 0:
                            closed = True
                            break
                        body_parts.append(character)
                    else:
                        body_parts.append(character)
                if closed:
                    break
                body_parts.append("\n")
            if not closed:
                continue
            body = "".join(body_parts)
            body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
            body = re.sub(r"//[^\n]*", "", body)
            if not body.strip():
                findings.append(catch_line)
    return findings


class MockProvider:
    async def review(self, chunks: list[ReviewChunk]) -> list[Finding]:
        findings: list[Finding] = []
        empty_catch_rule = Rule(
            "MOCK-004", "high", "correctness", "swallowed exception", re.compile("")
        )
        for chunk in chunks:
            for file_diff in chunk.files:
                for line in file_diff.added_lines:
                    for rule in RULES:
                        if rule.pattern.search(line.content):
                            findings.append(_finding(rule, line))
                findings.extend(
                    _finding(empty_catch_rule, line)
                    for line in _empty_catch_lines(file_diff)
                )
        return findings
