#!/usr/bin/env python3
"""Create an UNPUBLISHED draft comment on a change revision using gerrit-sdk-python.

Draft comments are private to their author: they are NOT published and do NOT notify
reviewers until a separate Review (Reply) is posted. This example only creates the
draft (PUT /a/changes/{id}/revisions/{rev}/drafts -> CommentInfo).

Authentication uses your ~/.gitcookies (the googlesource `o` cookie). Because git
rotates that cookie, the file can hold several `o` lines for one host; we keep the
last one per name (sending duplicates makes Gerrit answer 400).

Gerrit's )]}' XSSI guard is stripped by GerritApiClient (gerrit_xssi), a subclass of
the generated ApiClient -- no edit to generated code.

Examples:
  # A top-level draft on the commit message of patch set 3
  python examples/post-draft-comment/main.py 622261 --revision 3 \
      --path /COMMIT_MSG --line 7 --message "Nit: tighten this sentence."

  # A resolved reply that continues an existing thread
  python examples/post-draft-comment/main.py 622261 --revision 2 \
      --path java/.../JettyServer.java --line 337 --range 336:68-337:4 \
      --in-reply-to 800b1b8f_82a14609 --resolved --message "Done in PS3. Resolving."

  # Preview the DraftInput without sending it
  python examples/post-draft-comment/main.py 622261 --revision 2 \
      --path /COMMIT_MSG --line 24 --message "..." --dry-run
"""
import argparse
import os
import sys

from gerrit_client.api.changes_api import ChangesApi
from gerrit_client.configuration import Configuration
from gerrit_client.exceptions import ApiException
from gerrit_client.models.draft_input import DraftInput
from gerrit_client.models.range import Range
from gerrit_xssi import GerritApiClient


def cookie_header(path, domain):
    """Build a Cookie header from a git-cookies (Netscape-ish, tab-separated) file.

    Dedupe by cookie name, last occurrence wins: git rotates the `o` cookie and leaves
    stale duplicates behind; sending more than one `o` makes Gerrit reject the request.
    """
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


def parse_range(spec):
    """'sl:sc-el:ec' -> Range(start_line, start_character, end_line, end_character)."""
    try:
        start, end = spec.split("-")
        sl, sc = (int(x) for x in start.split(":"))
        el, ec = (int(x) for x in end.split(":"))
    except ValueError:
        raise SystemExit(f"--range must look like 336:68-337:4, got: {spec!r}")
    return Range(start_line=sl, start_character=sc, end_line=el, end_character=ec)


def build_client(base, cookies, anonymous, domain):
    config = Configuration(host=base.rstrip("/") + ("" if anonymous else "/a"))
    client = GerritApiClient(config)
    if not anonymous:
        client.cookie = cookie_header(cookies, domain)  # ApiClient sends this as Cookie
    return ChangesApi(client)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Create an unpublished Gerrit draft comment.")
    ap.add_argument("change", help="change number, Change-Id, or REST change id")
    ap.add_argument("--url", default="https://gerrit-review.googlesource.com")
    ap.add_argument("--revision", default="current",
                    help="revision id or patch-set number (default: current)")
    ap.add_argument("--path", required=True, help="file path, or /COMMIT_MSG, /PATCHSET_LEVEL")
    ap.add_argument("--message", help="comment body")
    ap.add_argument("--message-file", help="read the comment body from this file")
    ap.add_argument("--line", type=int, help="1-based line number (omit for file-level)")
    ap.add_argument("--range", dest="range_spec", help="sl:sc-el:ec character range")
    ap.add_argument("--in-reply-to", dest="in_reply_to", help="parent comment id (thread reply)")
    ap.add_argument("--side", choices=["REVISION", "PARENT"], help="comment side")
    res = ap.add_mutually_exclusive_group()
    res.add_argument("--resolved", dest="unresolved", action="store_false", default=None,
                     help="mark the thread resolved")
    res.add_argument("--unresolved", dest="unresolved", action="store_true", default=None,
                     help="mark the thread unresolved")
    ap.add_argument("--cookies", default="~/.gitcookies")
    ap.add_argument("--anonymous", action="store_true",
                    help="(cannot create drafts; useful only with --dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="print the DraftInput, do not send")
    args = ap.parse_args(argv)

    if args.message_file:
        args.message = open(os.path.expanduser(args.message_file)).read().rstrip("\n")
    if not args.message:
        ap.error("one of --message or --message-file is required")
    return args


def main(argv=None):
    args = parse_args(argv)
    domain = args.url.split("://", 1)[-1].split("/", 1)[0]

    draft = DraftInput(
        path=args.path,
        message=args.message,
        line=args.line,
        range=parse_range(args.range_spec) if args.range_spec else None,
        in_reply_to=args.in_reply_to,
        side=args.side,
        unresolved=args.unresolved,
    )

    if args.dry_run:
        print("DRY RUN -- would PUT this DraftInput (nothing sent):")
        print(f"  change={args.change} revision={args.revision}")
        print(draft.to_json())
        return

    api = build_client(args.url, args.cookies, args.anonymous, domain)
    try:
        res = api.put_changes_change_id_revisions_revision_id_drafts(
            args.change, args.revision, draft_input=draft
        )
    except ApiException as e:
        sys.exit(f"error creating draft: {e.status} {e.reason}\n{e.body}")

    print("DRAFT CREATED (unpublished):")
    for k in ("id", "path", "line", "in_reply_to", "unresolved", "updated"):
        print(f"  {k:<12}{getattr(res, k, None)}")
    print(f"  {'message':<12}{res.message}")


if __name__ == "__main__":
    main()
