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

echo "3/3 sync package version into the hand-written pyproject.toml"
python3 -c '
import re, sys
v = sys.argv[1]
s = open("pyproject.toml").read()
s = re.sub(r"^version = \".*\"", f"version = \"{v}\"", s, count=1, flags=re.M)
open("pyproject.toml", "w").write(s)
' "$PKG_VERSION"

echo "done: gerrit_client/ regenerated from $SPEC; XSSI handled by gerrit_xssi (no source patch)"
