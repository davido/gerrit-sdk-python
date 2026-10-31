#!/usr/bin/env bash
# Regenerate the Gerrit Python SDK from the OpenAPI document.
#
#   openapi-generator (python, pydantic v2)  ->  no source patching
#
# No generated-code patches: the one Gerrit-specific concern (the )]}' XSSI guard) is
# handled by the hand-written gerrit_xssi.GerritApiClient subclass, not by editing
# output. The python generator also maps the case-colliding query params O (scalar) / o
# (array) to distinct params on its own, so unlike the Rust SDK there is no query patch.
#
# Usage: ./generate.sh [path-or-url]   (default: ./rest-api-openapi.json)
set -euo pipefail
cd "$(dirname "$0")"
SPEC="${1:-rest-api-openapi.json}"

if [[ "$SPEC" == http://* || "$SPEC" == https://* ]]; then
  echo "0/3 fetch spec from $SPEC"
  curl -fsSL "$SPEC" -o rest-api-openapi.json
  SPEC=rest-api-openapi.json
fi

VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["info"]["version"])' "$SPEC")
# PEP 440 package version: -SNAPSHOT is not valid, so 3.15.0-SNAPSHOT -> 3.15.0.dev0.
# The git tag still mirrors the Gerrit version (v3.15.0-SNAPSHOT).
PKG_VERSION=$(python3 -c 'import sys; print(sys.argv[1].replace("-SNAPSHOT", ".dev0").lower())' "$VERSION")

echo "1/3 clean generated package"
rm -rf gerrit_client

echo "2/3 generate python client (Gerrit $VERSION -> package $PKG_VERSION)"
# pyproject.toml / README / gerrit_xssi / examples are protected by .openapi-generator-ignore.
npx --yes @openapitools/openapi-generator-cli@2.41.0 generate \
  -g python -i "$SPEC" -o . \
  --additional-properties=packageName=gerrit_client,projectName=gerrit-sdk-python,packageVersion="$PKG_VERSION" \
  >/dev/null

echo "3/4 sync package version into the hand-written pyproject.toml"
python3 -c '
import re, sys
v = sys.argv[1]
s = open("pyproject.toml").read()
s = re.sub(r"^version = \".*\"", f"version = \"{v}\"", s, count=1, flags=re.M)
open("pyproject.toml", "w").write(s)
' "$PKG_VERSION"

echo "4/4 sync Gerrit version + surface counts into the hand-written README.md"
# README.md is protected by .openapi-generator-ignore, so the generator never rewrites
# it. Keep its Gerrit-version tokens in step with the spec here, reusing the same
# VERSION/PKG_VERSION derived above (no second source of truth). The substitutions are
# anchored to the Gerrit-release context so they never touch unrelated versions
# (OkHttp, pydantic, generator-cli, urllib3, package deps). The "What's in this repo"
# surface counts (operations / API classes / models) are recomputed from the freshly
# generated package so they can never rot: operations = main op methods across api/*.py
# (each op also emits _with_http_info / _without_preload_content / _*_serialize helpers,
# which are excluded); API classes = api/*.py; models = models/*.py (both minus __init__).
python3 -c '
import re, sys, glob, os
VERSION, PKG_VERSION = sys.argv[1], sys.argv[2]

def mods(sub):
    return [p for p in glob.glob(f"gerrit_client/{sub}/*.py")
            if os.path.basename(p) != "__init__.py"]

api_files = mods("api")
model_count = len(mods("models"))
api_count = len(api_files)
op_count = 0
for p in api_files:
    for line in open(p):
        if (line.startswith("    def ") and "__init__" not in line
                and not re.search(r"_with_http_info|_without_preload_content|_serialize", line)):
            op_count += 1

s = open("README.md").read()
SNAP = r"\d+\.\d+\.\d+-SNAPSHOT"      # Gerrit snapshot form X.Y.Z-SNAPSHOT
DEV  = r"\d+\.\d+\.\d+(?:\.dev\d+)?"  # PEP 440 package form X.Y.Z[.devN]
# 1. "Gerrit X.Y.Z-SNAPSHOT" (bare version right after the word Gerrit).
s = re.sub(r"(Gerrit )" + SNAP, r"\g<1>" + VERSION, s)
# 2. "vX.Y.Z-SNAPSHOT" (git tag form: a v immediately before the version).
s = re.sub(r"(?<![\w.])v" + SNAP, "v" + VERSION, s)
# 3. the package version in backticks: `X.Y.Z.devN`.
s = re.sub(r"(`)" + DEV + r"(`)", r"\g<1>" + PKG_VERSION + r"\g<2>", s)
# 4. surface counts in the one "**N operations** across **M API classes** ... **K ... models**" line.
s = re.sub(r"\*\*\d+ operations\*\*",   f"**{op_count} operations**",    s)
s = re.sub(r"\*\*\d+ API classes\*\*",  f"**{api_count} API classes**",  s)
s = re.sub(r"\*\*\d+ pydantic models\*\*", f"**{model_count} pydantic models**", s)
open("README.md", "w").write(s)
' "$VERSION" "$PKG_VERSION"

echo "done: gerrit_client/ regenerated from $SPEC; XSSI handled by gerrit_xssi (no source patch)"
