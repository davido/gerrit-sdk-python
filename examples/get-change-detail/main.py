#!/usr/bin/env python3
"""Read a change with detail (GET /changes/{id} -> ChangeInfo, anonymous) and print a
colored, Web-UI-style summary using Gerrit's own palette -- the Python twin of the Rust
and Go examples. Every value comes from the generated gerrit_client models; only the
formatting is hand-written.

Gerrit's )]}' XSSI guard is stripped by GerritApiClient (gerrit_xssi), a subclass of the
generated ApiClient -- the one Gerrit-specific step, and no edit to generated code.

    python examples/get-change-detail/main.py --change 622261
"""
import argparse
import os
import sys

from gerrit_client.api.changes_api import ChangesApi
from gerrit_client.configuration import Configuration
from gerrit_client.exceptions import ApiException
from gerrit_xssi import GerritApiClient

OPTIONS = [
    "LABELS", "DETAILED_ACCOUNTS", "DETAILED_LABELS", "CURRENT_REVISION",
    "CURRENT_COMMIT", "CURRENT_FILES", "SUBMIT_REQUIREMENTS",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://gerrit-review.googlesource.com")
    ap.add_argument("--change", default="621763")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    global USE_COLOR
    USE_COLOR = compute_color(args.no_color)

    base = args.url.rstrip("/")
    config = Configuration(host=base)
    api = ChangesApi(GerritApiClient(config))
    try:
        ci = api.get_changes_change_id(args.change, o2=OPTIONS)
    except ApiException as e:
        sys.exit(f"error: {e}")
    print_change_details(base, ci)


# ---- presentation -------------------------------------------------------------

def print_change_details(base, ci):
    print(rule())
    print(f"  {status_badge(ci)}  {sgr('#' + str(ci.number or 0), BOLD)}")
    print(f"  {sgr(ci.subject or '', BOLD)}")
    print(rule())
    print(f"  {fg(f'{base}/c/{ci.project or ''}/+/{ci.number or 0}', BLUE_700)}")

    section("Change Info")
    row("Owner", account(ci.owner))
    commit = current_commit(ci)
    if commit is not None:
        row("Author", person(commit.author))
        row("Committer", person(commit.committer))
    row("Repo | Branch", f"{link(ci.project or '')} | {link(ci.branch or '')}")
    row("Change-Id", link(ci.change_id or ""))
    if ci.topic:
        row("Topic", link(ci.topic))
    if ci.hashtags:
        row("Hashtags", link(", ".join(ci.hashtags)))
    flags = flag_chips(ci)
    if flags:
        row("Flags", "  ".join(flags))
    row("Strategy", pascal(enum_value(ci.submit_type)))
    parent = parent_commit(ci)
    if parent:
        row("Parent", link(parent[:12]))
    row("Patch set", str(ci.current_revision_number or "?"))
    row("Updated", ci.updated or "")
    row("Size", plusminus(ci.insertions or 0, ci.deletions or 0))
    row("Comments", comments_summary(ci))

    # Reviewers / CC -- one account per line (no comma overflow).
    reviewers = ci.reviewers or {}
    for key, title in (("REVIEWER", "Reviewers"), ("CC", "CC")):
        people = reviewers.get(key) or []
        if not people:
            continue
        section(title)
        for a in people:
            print(f"    {account(a)}")

    if ci.submit_requirements:
        section("Submit Requirements")
        for r in ci.submit_requirements:
            icon, text = req_parts(enum_value(r.status))
            print(f"    {icon} {(r.name or ''):<26} {text}")

    if ci.labels:
        section("Votes")
        for name in sorted(ci.labels):
            chips = [
                vote_chip(a.value, a.name or "")
                for a in (ci.labels[name].all or [])
                if a.value  # only non-zero, like the UI aggregate
            ]
            value = "  ".join(chips) if chips else sgr("—", DIM)
            print(f"    {name:<22} {value}")

    files = current_files(ci)
    if files:
        section(f"Files (patch set {ci.current_revision_number or '?'})")
        # Commit message pseudo-file first, then the rest alphabetically -- like the UI.
        for p in sorted(files, key=lambda p: (p != "/COMMIT_MSG", p.lower())):
            f = files[p]
            letter, color = file_status(f.status)
            if p == "/COMMIT_MSG":
                name = "Commit message"
            elif f.old_path:
                name = f"{f.old_path} → {p}"
            else:
                name = p
            counts = plusminus(f.lines_inserted or 0, f.lines_deleted or 0)
            print(f"    {fg(letter, color)} {name:<52} {counts}")

    print(rule())


# ---- model accessors ----------------------------------------------------------

def current_commit(ci):
    cr = ci.current_revision
    revs = ci.revisions or {}
    rev = revs.get(cr) if cr else None
    return rev.commit if rev else None


def current_files(ci):
    cr = ci.current_revision
    revs = ci.revisions or {}
    rev = revs.get(cr) if cr else None
    return (rev.files or {}) if rev else {}


def parent_commit(ci):
    commit = current_commit(ci)
    if commit is None or not commit.parents:
        return ""
    return commit.parents[0].commit or ""


def account(a):
    if a is None:
        return "—"
    name, email = a.name, a.email
    if name and email:
        return named(name, email)
    if name:
        return sgr(name, BOLD)
    acc_id = getattr(a, "account_id", None)
    return f"account #{acc_id}" if acc_id else "—"


def person(p):
    if p is None or (not p.name and not p.email):
        return "—"
    return named(p.name or "", p.email or "")


def named(name, email):
    """Bold name, dim <email>. No blue -- reserve blue for links."""
    return f"{sgr(name, BOLD)} {sgr('<' + email + '>', DIM)}"


def flag_chips(ci):
    f = []
    if ci.work_in_progress:
        f.append(chip(" WIP ", WHITE, WIP_BROWN))
    if ci.is_private:
        f.append(chip(" Private ", WHITE, PURPLE_500))
    if ci.mergeable:
        f.append(fg("mergeable", GREEN_700))
    if ci.submittable:
        f.append(fg("submittable", GREEN_700))
    return f


def comments_summary(ci):
    total = ci.total_comment_count or 0
    unresolved = ci.unresolved_comment_count or 0
    resolved = max(total - unresolved, 0)
    open_color = RED_600 if unresolved > 0 else GREEN_700
    return (f"{total} total  ({fg(f'{resolved} resolved', GREEN_700)}, "
            f"{fg(f'{unresolved} unresolved', open_color)})")


def enum_value(x):
    if x is None:
        return ""
    return getattr(x, "value", str(x))


def pascal(s):
    """NOT_APPLICABLE -> NotApplicable, MERGE_IF_NECESSARY -> MergeIfNecessary."""
    return "".join(part.capitalize() for part in s.split("_"))


# ---- color / styling ----------------------------------------------------------
# Zero-dependency ANSI, disabled when stdout is not a TTY, on NO_COLOR, or --no-color.

USE_COLOR = False
BOLD = "1"
DIM = "2"

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
# Borrowed verbatim from Gerrit's Web UI theme (polygerrit-ui app-theme.ts).
GRAY_700 = (95, 99, 104)    # --status-merged / --status-abandoned / modified
YELLOW_700 = (242, 153, 0)  # --status-active (black text)
WIP_BROWN = (121, 85, 72)   # --status-wip
PURPLE_500 = (161, 66, 244)  # --status-private / rewrite files
GREEN_700 = (24, 128, 56)   # --status-ready / satisfied / additions
GREEN_300 = (129, 201, 149)  # --vote-color-approved chip bg
RED_300 = (242, 139, 130)   # --vote-color-rejected chip bg
RED_600 = (217, 48, 37)     # --status-conflict / deletions
BLUE_700 = (25, 103, 210)   # links / renamed files
HEADER_INDIGO = (62, 78, 138)  # Gerrit top-bar background, used for rules


def compute_color(no_color):
    if no_color or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CLICOLOR_FORCE"):  # force through a pipe
        return True
    return sys.stdout.isatty()


def sgr(s, code):
    return f"\x1b[{code}m{s}\x1b[0m" if USE_COLOR else s


def fg(s, rgb):
    return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{s}\x1b[0m" if USE_COLOR else s


def chip(s, fg_rgb, bg_rgb):
    if not USE_COLOR:
        return s
    return (f"\x1b[38;2;{fg_rgb[0]};{fg_rgb[1]};{fg_rgb[2]};"
            f"48;2;{bg_rgb[0]};{bg_rgb[1]};{bg_rgb[2]}m{s}\x1b[0m")


def link(s):
    return fg(s, BLUE_700)


def rule():
    return fg("─" * 76, HEADER_INDIGO)


def section(title):
    print()
    print(f"  {sgr(title.upper(), BOLD)}")


def row(label, value):
    # Pad the visible label to width BEFORE coloring -- ANSI escape bytes would
    # otherwise be counted and break column alignment when color is on.
    print(f"    {sgr(f'{label:<14}', DIM)}{value}")


def status_badge(ci):
    # Derive the display state the way gr-change-status does: the raw REST status is
    # only NEW/MERGED/ABANDONED, but an open change reads WIP or Private when those
    # flags are set, otherwise "Active".
    raw = enum_value(ci.status).upper()
    if raw == "MERGED":
        label, fg_c, bg = "Merged", WHITE, GRAY_700
    elif raw == "ABANDONED":
        label, fg_c, bg = "Abandoned", WHITE, GRAY_700
    elif ci.work_in_progress:
        label, fg_c, bg = "WIP", WHITE, WIP_BROWN
    elif ci.is_private:
        label, fg_c, bg = "Private", WHITE, PURPLE_500
    else:
        label, fg_c, bg = "Active", BLACK, YELLOW_700
    return chip(f" {label} ", fg_c, bg)


def vote_chip(v, who):
    bg = GREEN_300 if v > 0 else RED_300
    return f"{chip(f' {v:+d} ', BLACK, bg)} {who}"


def plusminus(ins, dele):
    return f"{fg(f'+{ins}', GREEN_700)} {fg(f'-{dele}', RED_600)}"


def req_parts(status):
    """(icon, colored status text) for a submit-requirement status (upper snake wire
    value); display it PascalCased."""
    display = pascal(status) if status else ""
    if status == "SATISFIED":
        return fg("✓", GREEN_700), fg(display, GREEN_700)
    if status == "UNSATISFIED":
        return fg("✗", RED_600), fg(display, RED_600)
    return sgr("○", DIM), sgr(display, DIM)  # NOT_APPLICABLE and others


def file_status(s):
    return {
        "A": ("A", GREEN_700),   # added
        "D": ("D", RED_600),     # deleted
        "R": ("R", BLUE_700),    # renamed
        "C": ("C", BLUE_700),    # copied
        "W": ("W", PURPLE_500),  # rewrite
    }.get(s, ("M", GRAY_700))    # modified


if __name__ == "__main__":
    main()
