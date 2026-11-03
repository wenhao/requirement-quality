from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "数据录入": ("10-数据录入", 8),
    "数据消费": ("20-数据消费", 7),
    "流程与状态": ("30-流程与状态", 5),
    "交互反馈": ("40-交互反馈", 4),
    "权限与安全": ("50-权限与安全", 6),
    "集成与接口": ("60-集成与接口", 4),
    "非功能": ("70-非功能", 7),
    "需求管理": ("80-需求管理", 2),
    "业务规则与数据": ("90-业务规则与数据", 2),
}
REQUIRED_RULE_FIELDS = {
    "type", "id", "title", "summary", "scenario", "group", "domain",
    "label", "triggers", "disclosure_level", "status", "confidence", "evidence",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)(?:#[^)\s]+)?\)")
LEGACY_PATH = re.compile(r"(?:场景|知识库|测评集)/|场景/INDEX\.md|^\./覆盖矩阵\.md")


def split_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


def markdown_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*.md"):
        if any(part in {".git", ".workbuddy", "scripts"} for part in path.parts):
            continue
        files.append(path)
    return files


def check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        for match in MARKDOWN_LINK.finditer(path.read_text(encoding="utf-8")):
            target = match.group(1)
            if re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
                continue
            candidate = (path.parent / target).resolve()
            try:
                candidate.relative_to(ROOT)
            except ValueError:
                errors.append(f"link escapes repo: {path.relative_to(ROOT)} -> {target}")
                continue
            if not candidate.exists():
                errors.append(f"broken link: {path.relative_to(ROOT)} -> {target}")
    return errors


def check_legacy_references(files: list[Path]) -> list[str]:
    errors = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if relative == "README.md":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if LEGACY_PATH.search(line):
                errors.append(f"legacy reference: {relative}:{number}")
    return errors


def check_domains() -> tuple[list[str], list[Path]]:
    errors: list[str] = []
    rules: list[Path] = []
    for domain, (directory, expected_count) in GROUPS.items():
        domain_path = ROOT / directory
        if not domain_path.is_dir():
            errors.append(f"missing domain directory: {directory}")
            continue
        for required in ("_index.md", "_domain-context.md"):
            if not (domain_path / required).is_file():
                errors.append(f"missing {directory}/{required}")
        domain_rules = sorted(domain_path.glob("规则-R-S*.md"))
        rules.extend(domain_rules)
        if len(domain_rules) != expected_count:
            errors.append(f"rule count mismatch: {directory} expected {expected_count}, got {len(domain_rules)}")
        context = (domain_path / "_domain-context.md").read_text(encoding="utf-8") if domain_path.joinpath("_domain-context.md").exists() else ""
        for rule in domain_rules:
            if rule.stem.removeprefix("规则-") not in context:
                errors.append(f"context pack missing rule: {rule.relative_to(ROOT)}")
        if directory not in (ROOT / "_index.md").read_text(encoding="utf-8"):
            errors.append(f"root index missing domain: {directory}")
    if len(rules) != 45:
        errors.append(f"total rule count expected 45, got {len(rules)}")
    return errors, rules


def check_rules(rules: list[Path]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    matrix = (ROOT / "96-治理/矩阵-规则覆盖.md").read_text(encoding="utf-8")
    for path in rules:
        relative = path.relative_to(ROOT).as_posix()
        fields = split_frontmatter(path)
        missing = REQUIRED_RULE_FIELDS - fields.keys()
        if missing:
            errors.append(f"missing frontmatter fields {sorted(missing)}: {relative}")
            continue
        rule_id = fields["id"]
        if rule_id in seen_ids:
            errors.append(f"duplicate rule id: {rule_id}")
        seen_ids.add(rule_id)
        if path.name != f"规则-{rule_id}.md":
            errors.append(f"filename does not match id: {relative}")
        if fields["type"] != "rule" or fields["disclosure_level"] != "L3" or fields["status"] != "confirmed":
            errors.append(f"invalid disclosure metadata: {relative}")
        if fields["domain"] not in GROUPS or fields["group"] != fields["domain"]:
            errors.append(f"domain mismatch: {relative}")
        evidence = ROOT / fields["evidence"]
        if not evidence.is_file():
            errors.append(f"missing evidence: {relative} -> {fields['evidence']}")
        if path.name not in matrix:
            errors.append(f"matrix missing rule: {path.name}")
    return errors


def check_manifest() -> list[str]:
    errors: list[str] = []
    manifest_path = ROOT / "_agent-manifest.yaml"
    if not manifest_path.is_file():
        return ["missing _agent-manifest.yaml"]
    manifest = manifest_path.read_text(encoding="utf-8")
    for directory in [value[0] for value in GROUPS.values()]:
        if f"path: {directory}" not in manifest:
            errors.append(f"manifest missing domain: {directory}")
    for required in ("schema_version:", "disclosure:", "entry: _index.md", "max_auto_pages: 8", "evidence: 99-证据", "learning: 95-学习旅程"):
        if required not in manifest:
            errors.append(f"manifest missing setting: {required}")
    return errors


def main() -> int:
    files = markdown_files()
    errors = check_links(files)
    errors.extend(check_legacy_references(files))
    domain_errors, rules = check_domains()
    errors.extend(domain_errors)
    errors.extend(check_rules(rules))
    errors.extend(check_manifest())
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"structure valid: {len(files)} markdown pages, {len(rules)} rules, 9 domains")
    return 0


if __name__ == "__main__":
    sys.exit(main())
