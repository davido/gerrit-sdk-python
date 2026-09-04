#!/usr/bin/env python3
"""Fetch a change's inline comments and change messages with gerrit-sdk-python and
render them chronologically -- the SDK twin of the standalone gerrit_get_comments.py.

Every value comes from generated gerrit_client models (CommentInfo, ChangeMessageInfo,
ChangeInfo); only the markdown/JSON shaping is hand-written. Gerrit's )]}' XSSI guard is
stripped by GerritApiClient (gerrit_xssi), a subclass of the generated ApiClient.

Authenticated reads (published comments of changes you can see, plus your own drafts)
use ~/.gitcookies. Pass --anonymous for the public, unauthenticated endpoints.

Examples:
  python examples/get-comments/main.py 622261
  python examples/get-comments/main.py 622261 --include-drafts -o comments.md
  python examples/get-comments/main.py 622261 --format json -o comments.json
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

from gerrit_client.api.changes_api import ChangesApi
from gerrit_client.configuration import Configuration
from gerrit_client.exceptions import ApiException
from gerrit_xssi import GerritApiClient

DEFAULT_URL = "https://gerrit-review.googlesource.com"
DETAIL_OPTIONS = ["ALL_REVISIONS", "CURRENT_COMMIT", "CURRENT_REVISION", "DETAILED_ACCOUNTS"]


# ---- auth / client ------------------------------------------------------------

def cookie_header(path, domain):
    """Cookie header from a git-cookies file; dedupe by name, last wins (git rotates
    the `o` cookie and sending duplicates makes Gerrit answer 400)."""
    latest = {}
    with open(os.path.expanduser(path)) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) != 7:
                fields = line.split()
            if len(fields) != 7:
                continue
            dom, _sub, _p, _secure, _exp, name, value = fields
            if dom == domain:
                latest[name] = value
    if not latest:
        sys.exit(f"No cookies for {domain} in {path}")
    return "; ".join(f"{n}={v}" for n, v in latest.items())


def build_api(base, cookies, anonymous):
    domain = base.split("://", 1)[-1].split("/", 1)[0]
    config = Configuration(host=base.rstrip("/") + ("" if anonymous else "/a"))
    client = GerritApiClient(config)
    if not anonymous:
        client.cookie = cookie_header(cookies, domain)
    return ChangesApi(client)


def change_id_from_arg(change):
    parsed = urlparse(change)
    if parsed.scheme and parsed.netloc:
        for pat in (r"/\+/([^/?#]+)", r"/c/[^/]+/([^/?#]+)"):
            m = re.search(pat, parsed.path)
            if m:
                return m.group(1)
        raise SystemExit(f"Could not find a Gerrit change id in URL: {change}")
    return change.strip()


def base_url_from_arg(change, url):
    parsed = urlparse(change)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return url


# ---- fetch --------------------------------------------------------------------

def fetch(api, change, include_drafts, anonymous):
    warnings = []
    # /changes/{id}?o=... rather than /detail: the generated _detail wrapper
    # deserializes to None, while get_changes_change_id returns a real ChangeInfo.
    detail = api.get_changes_change_id(change, o2=DETAIL_OPTIONS)
    comments = api.get_changes_change_id_comments(change)
    messages = api.get_changes_change_id_messages(change)

    robot_comments = {}
    try:
        robot_comments = api.get_changes_change_id_robotcomments(change)
    except ApiException as e:
        if e.status == 404:
            warnings.append("Optional endpoint not available: robotcomments")
        else:
            raise

    drafts = {}
    if include_drafts:
        if anonymous:
            warnings.append("--include-drafts ignored in --anonymous mode")
        else:
            drafts = api.get_changes_change_id_drafts(change)

    return {
        "detail": detail,
        "comments": comments or {},
        "messages": messages or [],
        "robot_comments": robot_comments or {},
        "drafts": drafts or {},
        "warnings": warnings,
    }


# ---- model accessors ----------------------------------------------------------

def account_name(a):
    if a is None:
        return "unknown"
    name = a.name or a.display_name or a.username or f"account {a.account_id}"
    return f"{name} <{a.email}>" if a.email else str(name)


def comment_location(c):
    parts = []
    if c.patch_set is not None:
        parts.append(f"PS{c.patch_set}")
    side = getattr(c.side, "value", c.side) if c.side is not None else None
    if side:
        parts.append(str(side))
    if c.parent is not None:
        parts.append(f"parent {c.parent}")
    if c.line is not None:
        parts.append(f"line {c.line}")
    r = c.range
    if r is not None:
        parts.append(f"range {r.start_line}:{r.start_character}-{r.end_line}:{r.end_character}")
    return ", ".join(parts) if parts else "file-level"


def flatten(comments):
    """{path: [CommentInfo]} -> [(path, CommentInfo)] sorted like the Web UI thread order."""
    flat = [(path, c) for path, entries in comments.items() for c in entries]
    return sorted(flat, key=lambda it: (
        it[1].patch_set or 0, it[0], it[1].line or 0, it[1].updated or "", it[1].id or ""))


def current_patch_set(detail):
    cr = detail.current_revision
    revs = detail.revisions or {}
    rev = revs.get(cr) if cr else None
    return getattr(rev, "number", None) if rev else None


# ---- markdown -----------------------------------------------------------------

def render_comment(path, c):
    state = "unresolved" if c.unresolved else "resolved"
    reply = f"; in reply to {c.in_reply_to}" if c.in_reply_to else ""
    return [
        f"### {path} - {comment_location(c)} - {state}{reply}",
        f"Author: {account_name(c.author)}",
        f"Updated: {c.updated or '-'}",
        "",
        (c.message or "_empty comment_").rstrip(),
        "",
    ]


def render_markdown(change_arg, data):
    d = data["detail"]
    inline = flatten(data["comments"])
    drafts = flatten(data["drafts"])
    robots = flatten(data["robot_comments"])

    lines = [
        f"# Gerrit change {d.number or change_arg} comment context",
        "",
        f"Subject: {d.subject or '-'}",
        f"Project: {d.project or '-'}  Branch: {d.branch or '-'}  Status: "
        f"{getattr(d.status, 'value', d.status) or '-'}",
        f"Change-Id: {d.change_id or '-'}",
        f"Current revision: {d.current_revision or '-'}",
    ]
    ps = current_patch_set(d)
    if ps is not None:
        lines.append(f"Current patch set: {ps}")
    lines.append("")

    if data["warnings"]:
        lines += ["## Warnings", ""]
        lines += [f"- {w}" for w in data["warnings"]]
        lines.append("")

    lines += [f"## Inline comments ({len(inline)})", ""]
    if inline:
        for path, c in inline:
            lines += render_comment(path, c)
    else:
        lines += ["_No published inline comments returned._", ""]

    if drafts:
        lines += [f"## Draft inline comments ({len(drafts)})", ""]
        for path, c in drafts:
            lines += render_comment(path, c)

    if robots:
        lines += [f"## Robot comments ({len(robots)})", ""]
        for path, c in robots:
            lines += render_comment(path, c)

    lines += [f"## Change messages ({len(data['messages'])})", ""]
    for m in data["messages"]:
        tag = f" tag={m.tag}" if m.tag else ""
        lines += [
            f"### {m.var_date or '-'} - PS{m.revision_number if m.revision_number is not None else '?'}"
            f" - {account_name(m.author)}{tag}",
            "",
            (m.message or "_empty message_").rstrip(),
            "",
        ]
    return "\n".join(lines)


# ---- json ---------------------------------------------------------------------

def _comments_to_dict(comments):
    return {path: [c.to_dict() for c in entries] for path, entries in comments.items()}


def render_json(change_arg, data):
    d = data["detail"]
    return json.dumps({
        "change": change_arg,
        "detail": d.to_dict(),
        "comments": _comments_to_dict(data["comments"]),
        "messages": [m.to_dict() for m in data["messages"]],
        "robot_comments": _comments_to_dict(data["robot_comments"]),
        "drafts": _comments_to_dict(data["drafts"]),
        "warnings": data["warnings"],
    }, indent=2, ensure_ascii=False, default=str)


# ---- cli ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Fetch Gerrit comments and change messages.")
    ap.add_argument("change", help="change number, Change-Id, REST id, or web URL")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--cookies", default="~/.gitcookies")
    ap.add_argument("--anonymous", action="store_true")
    ap.add_argument("--include-drafts", action="store_true")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    base = base_url_from_arg(args.change, args.url)
    change = change_id_from_arg(args.change)
    api = build_api(base, args.cookies, args.anonymous)

    try:
        data = fetch(api, change, args.include_drafts, args.anonymous)
    except ApiException as e:
        sys.exit(f"error: {e.status} {e.reason}\n{e.body}")

    text = render_json(change, data) if args.format == "json" else render_markdown(change, data)

    if args.output:
        with open(os.path.expanduser(args.output), "w") as fh:
            fh.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
