import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


RELEASE_HEADER_RE = re.compile(r"^## \[(?P<version>[^\]]+)\].*\((?P<date>\d{4}-\d{2}-\d{2})\)")
SECTION_HEADER_RE = re.compile(r"^### (?P<section>.+)$")
CHANGE_ITEM_RE = re.compile(r"^\* (?P<text>.+)$")
SCOPE_RE = re.compile(r"^[a-z]+(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<rest>.+)$", re.IGNORECASE)
TICKET_RE = re.compile(r"\b([A-Z]{2,}-\d+)\b")
PR_NUMBER_RE = re.compile(r"#(\d+)")
MERGE_PR_RE = re.compile(r"Merge pull request #(\d+) from ([^\s]+)")


def load_template(template_path: Path) -> dict:
    return json.loads(template_path.read_text(encoding="utf-8"))


def normalize_text(text: str) -> str:
    text = re.sub(r"\([^)]*github\.com[^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_scope_and_description(text: str) -> tuple[str, str]:
    normalized = normalize_text(text)
    match = SCOPE_RE.match(normalized)
    if not match:
        return "", normalized
    scope = (match.group("scope") or "").strip().lower()
    return scope, match.group("rest").strip()


def extract_latest_release_blocks(changelog_path: Path) -> tuple[str, str, list[tuple[str, str]]]:
    lines = changelog_path.read_text(encoding="utf-8").splitlines()
    version = ""
    release_date = ""
    active_section = ""
    items: list[tuple[str, str]] = []
    inside_latest = False

    for line in lines:
        header_match = RELEASE_HEADER_RE.match(line)
        if header_match:
            if inside_latest:
                break
            inside_latest = True
            version = header_match.group("version")
            release_date = header_match.group("date")
            continue

        if not inside_latest:
            continue

        section_match = SECTION_HEADER_RE.match(line)
        if section_match:
            active_section = section_match.group("section").strip()
            continue

        item_match = CHANGE_ITEM_RE.match(line)
        if item_match and active_section:
            items.append((active_section, item_match.group("text").strip()))

    return version, release_date, items


def format_date(iso_date: str) -> str:
    parsed = datetime.strptime(iso_date, "%Y-%m-%d")
    return parsed.strftime("%d/%m/%Y")


def build_entry(section: str, raw_item: str, config: dict) -> str:
    change_type = config["section_type_map"].get(section, "Melhoria")
    scope, description = extract_scope_and_description(raw_item)

    labels = [change_type]
    scope_map = config.get("scope_label_map", {})
    if scope and scope in scope_map:
        labels.append(scope_map[scope])

    for default_label in config.get("default_scope_labels", []):
        if default_label not in labels:
            labels.append(default_label)

    ticket_match = TICKET_RE.search(description)
    ticket = f" [{ticket_match.group(1)}]" if ticket_match else ""
    description = re.sub(TICKET_RE, "", description).strip(" -")
    pr_match = PR_NUMBER_RE.search(raw_item)
    branch = ""
    if pr_match:
        branch = config.get("_pr_branch_map", {}).get(pr_match.group(1), "")

    prefix = "".join(f"[{label}]" for label in labels)
    branch_suffix = f" [branch: {branch}]" if branch else ""
    return f"{prefix} - {description}{ticket}{branch_suffix}"


def load_pr_branch_map(repo_root: Path) -> dict[str, str]:
    result = subprocess.run(
        ["git", "log", "--merges", "--pretty=%s", "-n", "500"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}

    pr_branch_map: dict[str, str] = {}
    for line in result.stdout.splitlines():
        match = MERGE_PR_RE.search(line)
        if not match:
            continue
        pr_number = match.group(1)
        full_branch = match.group(2)
        pr_branch_map[pr_number] = full_branch
    return pr_branch_map


def render_block(version: str, release_date: str, entries: list[str]) -> str:
    body = "\n".join(entries) if entries else "[Interno] - Sem itens elegiveis para esta versao"
    return f"## {version}\n{format_date(release_date)}\n\n{body}\n"


def update_output_file(output_path: Path, product_name: str, version: str, block: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_path.exists():
        output_path.write_text(f"# {product_name}\n\n{block}\n", encoding="utf-8")
        return

    content = output_path.read_text(encoding="utf-8")
    if re.search(rf"^## {re.escape(version)}$", content, flags=re.MULTILINE):
        return

    header = f"# {product_name}\n\n"
    if content.startswith("# "):
        parts = content.split("\n\n", 1)
        rest = parts[1] if len(parts) > 1 else ""
        output_path.write_text(f"{header}{block}\n{rest}".rstrip() + "\n", encoding="utf-8")
    else:
        output_path.write_text(f"{header}{block}\n{content}".rstrip() + "\n", encoding="utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    template_path = repo_root / "changelog-template.json"
    changelog_path = repo_root / "CHANGELOG.md"
    if not changelog_path.exists():
        raise SystemExit("CHANGELOG.md nao encontrado. Rode release-please primeiro.")

    config = load_template(template_path)
    config["_pr_branch_map"] = load_pr_branch_map(repo_root)
    version, release_date, items = extract_latest_release_blocks(changelog_path)
    if not version:
        raise SystemExit("Nao foi possivel localizar a secao mais recente em CHANGELOG.md.")

    entries = [build_entry(section, item, config) for section, item in items]
    block = render_block(version, release_date, entries)
    output_path = repo_root / config["output_path"]
    update_output_file(output_path, config["product_name"], version, block)


if __name__ == "__main__":
    main()
