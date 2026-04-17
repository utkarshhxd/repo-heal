from __future__ import annotations

import difflib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

import httpx

from . import db, github
from .config import BACKEND_ROOT, get_settings


settings = get_settings()
HTMLHINT_CONFIG = BACKEND_ROOT / "config" / "htmlhint.json"
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", "coverage"}
STATIC_SUFFIXES = (".html", ".htm", ".css", ".js")
KNOWN_HTML_TAGS = {
    "a",
    "abbr",
    "address",
    "area",
    "article",
    "aside",
    "audio",
    "b",
    "base",
    "bdi",
    "bdo",
    "blockquote",
    "body",
    "br",
    "button",
    "canvas",
    "caption",
    "cite",
    "code",
    "col",
    "colgroup",
    "data",
    "datalist",
    "dd",
    "del",
    "details",
    "dfn",
    "dialog",
    "div",
    "dl",
    "dt",
    "em",
    "embed",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hgroup",
    "hr",
    "html",
    "i",
    "iframe",
    "img",
    "input",
    "ins",
    "kbd",
    "label",
    "legend",
    "li",
    "link",
    "main",
    "map",
    "mark",
    "meta",
    "meter",
    "nav",
    "noscript",
    "object",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "picture",
    "pre",
    "progress",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "script",
    "search",
    "section",
    "select",
    "slot",
    "small",
    "source",
    "span",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "template",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "track",
    "u",
    "ul",
    "var",
    "video",
    "wbr",
}


def _configured_ollama_models() -> list[str]:
    candidates = [item.strip() for item in settings.ollama_model.split(",") if item.strip()]
    return candidates or ["qwen2.5-coder:14b"]


async def _available_ollama_models() -> list[str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{settings.ollama_base_url}/api/tags")
        response.raise_for_status()
        payload = response.json()
    return [item["name"] for item in payload.get("models", [])]


async def _generate_with_ollama(prompt: str, *, force_json: bool) -> dict[str, Any]:
    installed_models = await _available_ollama_models()
    candidate_models = _configured_ollama_models()
    fallback_models = [model for model in installed_models if model not in candidate_models]
    last_error: Exception | None = None

    for model in candidate_models + fallback_models:
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                print("\n=== OLLAMA PROMPT START ===\n")
                print(prompt)
                print("\n=== OLLAMA PROMPT END ===\n")
                payload: dict[str, Any] = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                }
                if force_json:
                    payload["format"] = "json"
                response = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
                response.raise_for_status()
                body = response.json()
                parsed = json.loads(body["response"])
                parsed["_model"] = model
                return parsed
            except Exception as exc:
                last_error = exc
                continue

    raise RuntimeError(f"Ollama generation failed for all candidate models. Last error: {last_error}")


def _tool_bin(name: str) -> str:
    bin_dir = BACKEND_ROOT / "node_modules" / ".bin"
    suffix = ".cmd" if os.name == "nt" else ""
    return str(bin_dir / f"{name}{suffix}")


def _handle_rmtree_error(func: Any, path: str, exc_info: Any) -> None:
    if not os.path.exists(path):
        return
    os.chmod(path, 0o700)
    func(path)


def cleanup_workspace(path: Path) -> None:
    if not path.exists():
        return
    shutil.rmtree(path, onerror=_handle_rmtree_error)


def _run(command: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Command failed")
    return completed


def _issue_signature(issue: dict[str, Any]) -> str:
    return "|".join(
        [
            issue["tool"],
            issue["file"],
            str(issue.get("rule") or ""),
            issue["message"],
            str(issue.get("line") or ""),
        ]
    )


def _relative_static_files(repo_path: Path, suffixes: tuple[str, ...]) -> list[str]:
    files: list[str] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(repo_path).parts):
            continue
        if path.suffix.lower() in suffixes:
            files.append(str(path.relative_to(repo_path)).replace("\\", "/"))
    return sorted(files)


def discover_static_site(repo_path: Path) -> dict[str, list[str]]:
    html_files = _relative_static_files(repo_path, (".html", ".htm"))
    css_files = _relative_static_files(repo_path, (".css",))
    js_files = _relative_static_files(repo_path, (".js",))
    return {"html": html_files, "css": css_files, "js": js_files}


def _is_local_reference(value: str) -> bool:
    if not value:
        return False
    if value.startswith("#"):
        return False
    if value.startswith("data:"):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "" and parsed.netloc == ""


def _sanitize_reference(value: str) -> str:
    return value.split("#", 1)[0].split("?", 1)[0]


def _resolve_reference(file_path: Path, reference: str) -> Path:
    cleaned = _sanitize_reference(reference)
    return (file_path.parent / cleaned).resolve()


def _reference_suggestion(file_path: Path, reference: str) -> str | None:
    cleaned = _sanitize_reference(reference)
    if not cleaned:
        return None

    target_path = (file_path.parent / cleaned)
    candidates: list[Path] = []
    if (target_path / "index.html").exists():
        candidates.append((target_path / "index.html").resolve())

    stem = target_path.stem
    parent = target_path.parent
    if parent.exists():
        for item in parent.iterdir():
            if item.is_file() and item.stem == stem:
                candidates.append(item.resolve())

    if not candidates:
        return None

    suggestion = candidates[0]
    return str(suggestion.relative_to(file_path.parent).as_posix())


class HtmlAuditParser(HTMLParser):
    def __init__(self, relative_path: str) -> None:
        super().__init__(convert_charrefs=True)
        self.relative_path = relative_path
        self.issues: list[dict[str, Any]] = []
        self.references: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._inspect_tag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._inspect_tag(tag, attrs)

    def handle_comment(self, data: str) -> None:
        if "<" in data and ">" in data:
            line, column = self.getpos()
            self.issues.append(
                {
                    "tool": "html-audit",
                    "file": self.relative_path,
                    "line": line,
                    "column": column + 1,
                    "message": "HTML comment contains raw tag-like markup.",
                    "rule": "suspicious-comment",
                }
            )

    def _inspect_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line, column = self.getpos()
        attrs_map = {name: value for name, value in attrs}

        if tag not in KNOWN_HTML_TAGS:
            suggestion = difflib.get_close_matches(tag, KNOWN_HTML_TAGS, n=1, cutoff=0.74)
            message = f"Unknown HTML tag <{tag}>."
            issue = {
                "tool": "html-audit",
                "file": self.relative_path,
                "line": line,
                "column": column + 1,
                "message": message,
                "rule": "unknown-tag",
                "tag": tag,
            }
            if suggestion:
                issue["suggestion"] = suggestion[0]
            self.issues.append(issue)

        if tag == "img" and not attrs_map.get("alt"):
            self.issues.append(
                {
                    "tool": "html-audit",
                    "file": self.relative_path,
                    "line": line,
                    "column": column + 1,
                    "message": "Image tag is missing alt text.",
                    "rule": "img-missing-alt",
                }
            )

        if tag == "link" and attrs_map.get("rel") == "stylesheet" and not attrs_map.get("href"):
            self.issues.append(
                {
                    "tool": "html-audit",
                    "file": self.relative_path,
                    "line": line,
                    "column": column + 1,
                    "message": "Stylesheet link is missing href.",
                    "rule": "missing-href",
                }
            )

        if tag == "script" and attrs_map.get("src") == "":
            self.issues.append(
                {
                    "tool": "html-audit",
                    "file": self.relative_path,
                    "line": line,
                    "column": column + 1,
                    "message": "Script tag has an empty src attribute.",
                    "rule": "empty-src",
                }
            )

        for attr_name in ("href", "src"):
            value = attrs_map.get(attr_name)
            if value is None or not _is_local_reference(value):
                continue
            self.references.append(
                {
                    "tag": tag,
                    "attribute": attr_name,
                    "value": value,
                    "line": line,
                    "column": column + 1,
                }
            )


def _lint_js(repo_path: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    targets = files or _relative_static_files(repo_path, (".js",))
    if not targets:
        return []

    command = [
        _tool_bin("eslint"),
        "--no-eslintrc",
        "--env",
        "browser,es2021",
        "--parser-options",
        "ecmaVersion:2022",
        "--rule",
        "no-undef:error",
        "--rule",
        "no-unused-vars:warn",
        "--rule",
        "no-console:warn",
        "--rule",
        "semi:error",
        "--format",
        "json",
        *targets,
    ]
    completed = _run(command, cwd=repo_path, check=False)
    payload = completed.stdout.strip() or "[]"
    results = json.loads(payload)
    issues: list[dict[str, Any]] = []
    for entry in results:
        for message in entry.get("messages", []):
            issues.append(
                {
                    "tool": "eslint",
                    "file": str(Path(entry["filePath"]).relative_to(repo_path)).replace("\\", "/"),
                    "line": message.get("line") or 1,
                    "column": message.get("column") or 1,
                    "message": message["message"],
                    "rule": message.get("ruleId") or "eslint",
                }
            )
    return issues


def _lint_html(repo_path: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    targets = files or _relative_static_files(repo_path, (".html", ".htm"))
    if not targets:
        return []

    command = [_tool_bin("htmlhint"), "--config", str(HTMLHINT_CONFIG), "--format", "json", *targets]
    completed = _run(command, cwd=repo_path, check=False)
    payload = completed.stdout.strip() or "[]"
    results = json.loads(payload)
    issues: list[dict[str, Any]] = []
    for entry in results:
        entry_path = Path(entry["file"])
        try:
            relative_file = str(entry_path.relative_to(repo_path)).replace("\\", "/")
        except ValueError:
            relative_file = entry["file"].replace("\\", "/")
        for message in entry.get("messages", []):
            rule_data = message.get("rule")
            issues.append(
                {
                    "tool": "htmlhint",
                    "file": relative_file,
                    "line": message.get("line") or 1,
                    "column": message.get("col") or 1,
                    "message": message["message"],
                    "rule": rule_data.get("id") if isinstance(rule_data, dict) else "htmlhint",
                }
            )
    return issues


def _lint_css(repo_path: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    targets = files or _relative_static_files(repo_path, (".css",))
    issues: list[dict[str, Any]] = []
    for relative_path in targets:
        file_path = repo_path / relative_path
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines, start=1):
            if "colr:" in line:
                issues.append(
                    {
                        "tool": "css-check",
                        "file": relative_path,
                        "line": index,
                        "column": line.index("colr:") + 1,
                        "message": "Unknown CSS property 'colr'.",
                        "rule": "unknown-property",
                    }
                )
            if re.search(r":\s*[^;{}]+$", line.strip()) and index < len(lines) and lines[index].strip() == "}":
                issues.append(
                    {
                        "tool": "css-check",
                        "file": relative_path,
                        "line": index,
                        "column": 1,
                        "message": "Missing semicolon before closing brace.",
                        "rule": "missing-semicolon",
                    }
                )
    return issues


def _custom_html_issues(repo_path: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    targets = files or _relative_static_files(repo_path, (".html", ".htm"))
    issues: list[dict[str, Any]] = []
    for relative_path in targets:
        file_path = repo_path / relative_path
        content = file_path.read_text(encoding="utf-8")
        parser = HtmlAuditParser(relative_path)
        parser.feed(content)
        parser.close()

        issues.extend(parser.issues)

        for reference in parser.references:
            resolved = _resolve_reference(file_path, reference["value"])
            if not resolved.exists():
                issue = {
                    "tool": "html-audit",
                    "file": relative_path,
                    "line": reference["line"],
                    "column": reference["column"],
                    "message": f"Broken local reference '{reference['value']}'.",
                    "rule": "broken-local-reference",
                    "reference": reference["value"],
                    "attribute": reference["attribute"],
                    "tag": reference["tag"],
                }
                suggestion = _reference_suggestion(file_path, reference["value"])
                if suggestion:
                    issue["suggestion"] = suggestion
                issues.append(issue)
    return issues


def _browser_smoke_issues(repo_path: Path, site_map: dict[str, list[str]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    html_files = site_map["html"]
    for relative_path in html_files:
        content = (repo_path / relative_path).read_text(encoding="utf-8")
        if "<body" in content.lower() and "</body>" not in content.lower():
            issues.append(
                {
                    "tool": "render-check",
                    "file": relative_path,
                    "line": 1,
                    "column": 1,
                    "message": "Page body appears to be unterminated.",
                    "rule": "unterminated-body",
                }
            )
        if "<head" in content.lower() and "</head>" not in content.lower():
            issues.append(
                {
                    "tool": "render-check",
                    "file": relative_path,
                    "line": 1,
                    "column": 1,
                    "message": "Page head appears to be unterminated.",
                    "rule": "unterminated-head",
                }
            )
    return issues


def collect_issues(repo_path: Path, file_hint: str | None = None) -> list[dict[str, Any]]:
    site_map = discover_static_site(repo_path)
    issues: list[dict[str, Any]] = []
    if file_hint is None or file_hint.endswith(".js"):
        issues.extend(_lint_js(repo_path, [file_hint] if file_hint and file_hint.endswith(".js") else None))
    if file_hint is None or file_hint.endswith((".html", ".htm")):
        html_files = [file_hint] if file_hint and file_hint.endswith((".html", ".htm")) else None
        issues.extend(_lint_html(repo_path, html_files))
        issues.extend(_custom_html_issues(repo_path, html_files))
    if file_hint is None or file_hint.endswith(".css"):
        issues.extend(_lint_css(repo_path, [file_hint] if file_hint and file_hint.endswith(".css") else None))
    if file_hint is None:
        issues.extend(_browser_smoke_issues(repo_path, site_map))

    deduped: dict[str, dict[str, Any]] = {}
    for issue in issues:
        deduped[_issue_signature(issue)] = issue
    return sorted(deduped.values(), key=lambda item: (item["file"], item["line"], item["column"], item["tool"]))


def extract_snippet(file_path: Path, line_number: int, context: int = 6) -> tuple[str, int, int]:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    start = max(0, line_number - context - 1)
    end = min(len(lines), line_number + context)
    snippet = "\n".join(lines[start:end])
    return snippet, start + 1, end


def apply_replacement(file_path: Path, start_line: int, end_line: int, replacement: str) -> None:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    lines[start_line - 1 : end_line] = replacement.splitlines()
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _is_parse_error(issue: dict[str, Any]) -> bool:
    message = issue["message"].lower()
    return "parsing error" in message or "unexpected token" in message or "unexpected end of input" in message


def _extract_js_function_names(content: str) -> set[str]:
    names = set(re.findall(r"function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", content))
    names.update(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*\(", content))
    names.update(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*\([^)]*\)\s*=>", content))
    return names


def _has_suspicious_file_reduction(original: str, updated: str, issue: dict[str, Any]) -> str | None:
    original_lines = original.splitlines()
    updated_lines = updated.splitlines()
    original_nonempty = [line for line in original_lines if line.strip()]
    updated_nonempty = [line for line in updated_lines if line.strip()]

    if original_nonempty and len(updated_nonempty) < max(4, int(len(original_nonempty) * 0.7)):
        return "the candidate removed too much of the file"

    if len(updated) < max(80, int(len(original) * 0.7)):
        return "the candidate shrank the file too aggressively"

    if issue["file"].endswith(".js"):
        original_functions = _extract_js_function_names(original)
        updated_functions = _extract_js_function_names(updated)
        lost_functions = sorted(original_functions - updated_functions)
        if lost_functions:
            return f"the candidate removed function definitions: {', '.join(lost_functions[:5])}"

    return None


def _repo_level_safety_check(repo_path: Path, fixed_files: set[str]) -> str | None:
    for relative_path in sorted(fixed_files):
        file_path = repo_path / relative_path
        if not file_path.exists():
            return f"{relative_path} is missing after fixes"

        content = file_path.read_text(encoding="utf-8")
        if file_path.suffix.lower() == ".js":
            if len([line for line in content.splitlines() if line.strip()]) < 8:
                return f"{relative_path} became unexpectedly short"
            function_names = _extract_js_function_names(content)
            if not function_names:
                return f"{relative_path} no longer contains any function definitions"

        if file_path.suffix.lower() in {".html", ".htm"}:
            if "<body" in content.lower() and "</body>" not in content.lower():
                return f"{relative_path} has an unterminated body tag"
    return None


def _replace_tag_name(content: str, old_tag: str, new_tag: str) -> str:
    content = re.sub(rf"(<\s*){re.escape(old_tag)}(\b)", rf"\1{new_tag}\2", content)
    content = re.sub(rf"(<\s*/\s*){re.escape(old_tag)}(\b)", rf"\1{new_tag}\2", content)
    return content


def attempt_rule_based_fix(repo_path: Path, issue: dict[str, Any]) -> bool:
    file_path = repo_path / issue["file"]
    original = file_path.read_text(encoding="utf-8")
    updated = original

    if issue["tool"] in {"htmlhint", "html-audit"} and "title" in issue["message"].lower() and "<title" not in original.lower():
        updated = re.sub(r"<head([^>]*)>", r"<head\1>\n  <title>Auto fixed page</title>", updated, count=1, flags=re.IGNORECASE)
    elif issue.get("rule") in {"alt-require", "img-missing-alt"}:
        updated = re.sub(r"<img(?![^>]*\balt=)([^>]*)>", r'<img\1 alt="image">', updated, count=1, flags=re.IGNORECASE)
    elif issue["tool"] == "htmlhint" and "doctype" in issue["message"].lower() and "<!doctype" not in original.lower():
        updated = "<!DOCTYPE html>\n" + updated.lstrip()
    elif issue["tool"] == "eslint" and issue.get("rule") == "no-console":
        updated = re.sub(r"^\s*console\.log\(.*?\);\s*$\n?", "", updated, flags=re.MULTILINE)
    elif issue["tool"] == "css-check" and issue.get("rule") == "unknown-property":
        updated = updated.replace("colr:", "color:")
    elif issue["tool"] == "css-check" and issue.get("rule") == "missing-semicolon":
        lines = updated.splitlines()
        idx = issue["line"] - 1
        lines[idx] = lines[idx] + ";"
        updated = "\n".join(lines) + "\n"
    elif issue["tool"] == "html-audit" and issue.get("rule") == "unknown-tag" and issue.get("suggestion"):
        old_tag = issue.get("tag")
        if old_tag:
            updated = _replace_tag_name(updated, old_tag, issue["suggestion"])
    elif issue["tool"] == "html-audit" and issue.get("rule") == "broken-local-reference" and issue.get("suggestion"):
        reference = issue.get("reference")
        updated = updated.replace(reference, issue["suggestion"])

    if updated != original:
        file_path.write_text(updated, encoding="utf-8")
        return True
    return False


async def generate_llm_patch(issue: dict[str, Any], snippet: str, start_line: int, end_line: int) -> dict[str, Any]:
    prompt = f"""
You are fixing one issue in a static website repository.

Issue tool: {issue["tool"]}
Issue rule: {issue.get("rule") or "unknown"}
Issue message: {issue["message"]}
Target file: {issue["file"]}
Issue line: {issue["line"]}

Return only valid JSON with this exact shape:
{{
  "start_line": {start_line},
  "end_line": {end_line},
  "replacement": "corrected code only"
}}

Rules:
- Fix only the issue and keep surrounding behavior intact.
- Do not add markdown fences.
- Keep indentation reasonable.

Snippet:
{snippet}
""".strip()

    return await _generate_with_ollama(prompt, force_json=True)


async def generate_llm_file_rewrite(issue: dict[str, Any], file_path: Path) -> str:
    content = file_path.read_text(encoding="utf-8")
    prompt = f"""
You are fixing one static website file.

Issue tool: {issue["tool"]}
Issue rule: {issue.get("rule") or "unknown"}
Issue message: {issue["message"]}
Target file: {issue["file"]}

Return only valid JSON:
{{
  "replacement": "full corrected file content"
}}

Rules:
- Return the full corrected file.
- Fix the reported issue and preserve unrelated content.
- Do not add markdown fences or commentary.

File content:
{content}
""".strip()

    parsed = await _generate_with_ollama(prompt, force_json=True)
    return parsed["replacement"]


async def apply_llm_fix(repo_path: Path, issue: dict[str, Any]) -> None:
    file_path = repo_path / issue["file"]
    if file_path.suffix.lower() in {".html", ".htm"} or _is_parse_error(issue):
        replacement = await generate_llm_file_rewrite(issue, file_path)
        file_path.write_text(replacement.strip() + "\n", encoding="utf-8")
        return

    snippet, start_line, end_line = extract_snippet(file_path, issue["line"])
    patch = await generate_llm_patch(issue, snippet, start_line, end_line)
    apply_replacement(file_path, int(patch["start_line"]), int(patch["end_line"]), patch["replacement"])


def _authenticated_remote_url(repo_full_name: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repo_full_name}.git"


def clone_repo(repo_full_name: str, branch: str, token: str, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["git", "clone", "--depth", "1", "--branch", branch, _authenticated_remote_url(repo_full_name, token), str(target_path)],
        cwd=target_path.parent,
    )


def commit_and_push(repo_path: Path, fix_branch: str) -> None:
    _run(["git", "checkout", "-b", fix_branch], cwd=repo_path)
    _run(["git", "config", "user.name", settings.git_author_name], cwd=repo_path)
    _run(["git", "config", "user.email", settings.git_author_email], cwd=repo_path)
    _run(["git", "add", "."], cwd=repo_path)
    _run(["git", "commit", "-m", "fix: resolve static analysis issues"], cwd=repo_path)
    _run(["git", "push", "origin", fix_branch], cwd=repo_path)


async def run_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if job is None:
        return

    workspace = settings.workspace_root / job_id
    repo_path = workspace / "repo"
    token = db.get_access_token_for_user(job["user_id"])

    def log(message: str) -> None:
        db.append_job_log(job_id, message)

    try:
        db.update_job(job_id, status="cloning")
        log(f"Cloning {job['repo_full_name']} on branch {job['base_branch']}.")
        clone_repo(job["repo_full_name"], job["base_branch"], token, repo_path)

        db.update_job(job_id, status="analyzing")
        site_map = discover_static_site(repo_path)
        log(f"Repository cloned to {repo_path}.")
        log(
            "Discovered "
            f"{len(site_map['html'])} HTML, {len(site_map['css'])} CSS, and {len(site_map['js'])} JS file(s)."
        )
        if site_map["html"] or site_map["css"] or site_map["js"]:
            preview = site_map["html"][:3] + site_map["css"][:3] + site_map["js"][:3]
            log("Static files preview: " + ", ".join(preview))
        issues = collect_issues(repo_path)
        log(f"Validator stack found {len(issues)} issue(s) across static files.")

        fixed_files: set[str] = set()
        fixed_issue_messages: list[str] = []
        skipped_issues: list[str] = []
        skipped_signatures: set[str] = set()

        db.update_job(job_id, status="fixing")
        while True:
            current_issues = collect_issues(repo_path)
            pending_issues = [issue for issue in current_issues if _issue_signature(issue) not in skipped_signatures]
            if not pending_issues:
                break

            issue = pending_issues[0]
            file_path = repo_path / issue["file"]
            before_file_issues = [item for item in collect_issues(repo_path, issue["file"]) if item["tool"] == issue["tool"]]
            original_content = file_path.read_text(encoding="utf-8")
            log(f"Processing {issue['file']}:{issue['line']} {issue['message']}")

            changed = attempt_rule_based_fix(repo_path, issue)
            if changed:
                log(f"Applied rule-based fix for {issue['file']}.")
            else:
                try:
                    await apply_llm_fix(repo_path, issue)
                    log(f"Applied LLM fix candidate for {issue['file']}.")
                except Exception as exc:
                    skipped_signatures.add(_issue_signature(issue))
                    skipped_issues.append(f"{issue['file']}: {issue['message']}")
                    log(f"Skipped {issue['file']}:{issue['line']} because the LLM call failed: {exc}")
                    continue

            updated_content = file_path.read_text(encoding="utf-8")
            reduction_reason = _has_suspicious_file_reduction(original_content, updated_content, issue)
            if reduction_reason:
                file_path.write_text(original_content, encoding="utf-8")
                skipped_signatures.add(_issue_signature(issue))
                skipped_issues.append(f"{issue['file']}: {issue['message']}")
                log(f"Rejected fix for {issue['file']}:{issue['line']} because {reduction_reason}.")
                continue

            after_file_issues = [item for item in collect_issues(repo_path, issue["file"]) if item["tool"] == issue["tool"]]
            target_signature = _issue_signature(issue)
            before_signatures = {_issue_signature(item) for item in before_file_issues}
            after_signatures = {_issue_signature(item) for item in after_file_issues}

            if target_signature not in after_signatures and len(after_signatures) <= len(before_signatures):
                fixed_files.add(issue["file"])
                fixed_issue_messages.append(f"{issue['file']}: {issue['message']}")
                log(f"Accepted fix for {issue['file']}:{issue['line']}.")
            else:
                file_path.write_text(original_content, encoding="utf-8")
                skipped_signatures.add(target_signature)
                skipped_issues.append(f"{issue['file']}: {issue['message']}")
                log(f"Rejected fix for {issue['file']}:{issue['line']} after validation.")

        if not fixed_files:
            summary = {
                "fixed_count": 0,
                "skipped_count": len(skipped_issues) or len(issues),
                "fixed_files": [],
                "skipped_issues": skipped_issues or [f"{item['file']}: {item['message']}" for item in issues],
            }
            db.update_job(job_id, status="completed", summary_json=json.dumps(summary))
            log("No validated fixes were accepted, so no PR was created.")
            return

        repo_safety_error = _repo_level_safety_check(repo_path, fixed_files)
        if repo_safety_error:
            summary = {
                "fixed_count": 0,
                "skipped_count": len(skipped_issues) + len(fixed_issue_messages),
                "fixed_files": [],
                "skipped_issues": skipped_issues + fixed_issue_messages,
            }
            db.update_job(job_id, status="completed", summary_json=json.dumps(summary))
            log(f"Aborted PR creation because the repo-level safety check failed: {repo_safety_error}")
            return

        db.update_job(job_id, status="committing")
        fix_branch = f"agent/fix-{job_id[:8]}"
        log(f"Creating branch {fix_branch} and pushing changes.")
        commit_and_push(repo_path, fix_branch)

        db.update_job(job_id, status="creating_pr", fix_branch=fix_branch)
        log("Creating pull request.")
        pr = await github.create_pull_request(
            token,
            job["repo_full_name"],
            title=f"Agent fix: {len(fixed_issue_messages)} issue(s) resolved",
            body="\n".join(
                [
                    "## Automated Fix Summary",
                    "",
                    f"- Fixed issues: {len(fixed_issue_messages)}",
                    f"- Skipped issues: {len(skipped_issues)}",
                    "",
                    "### Accepted fixes",
                    *[f"- {entry}" for entry in fixed_issue_messages],
                    "",
                    "### Skipped",
                    *([f"- {entry}" for entry in skipped_issues] if skipped_issues else ["- None"]),
                ]
            ),
            head=fix_branch,
            base=job["base_branch"],
        )

        summary = {
            "fixed_count": len(fixed_issue_messages),
            "skipped_count": len(skipped_issues),
            "fixed_files": sorted(fixed_files),
            "skipped_issues": skipped_issues,
        }
        db.update_job(
            job_id,
            status="completed",
            summary_json=json.dumps(summary),
            pr_url=pr["html_url"],
            pr_number=pr["number"],
        )
        log(f"Pull request created: {pr['html_url']}")
    except Exception as exc:
        db.update_job(job_id, status="failed", error=str(exc))
        log(f"Job failed: {exc}")
    finally:
        try:
            cleanup_workspace(workspace)
        except Exception as exc:
            log(f"Workspace cleanup warning: {exc}")
