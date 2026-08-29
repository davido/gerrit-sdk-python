# gerrit-sdk-python

A **generated Python SDK** for the Gerrit Code Review REST API (the `gerrit_client`
package), produced from Gerrit's statically generated **OpenAPI 3.1** document. No
hand-written request/response types: every operation and model comes from the spec, so
the client never drifts from the server.

## The pipeline (end to end)

```
  gerrit                     gerrit-sdk-python              examples/
  (emit the spec)      -->    (this repo: the SDK)    -->    (consume the SDK)
  parse-only OpenAPI          openapi-generator (python)     python, live calls,
  emitter                     + XSSI subclass                colored output
```

1. **gerrit emits the spec.** A parse-only emitter (`java/com/google/gerrit/openapi/**`)
   reads the server's REST bindings via the javac Compiler Tree API — no running
   server, no reflection — and writes an OpenAPI 3.1 JSON.
2. **This repo pins that spec.** `rest-api-openapi.json` is a checked-in snapshot of
   that emitter's output.
3. **`generate.sh` generates the package.** openapi-generator (python, pydantic v2)
   turns the spec into `gerrit_client/`.
4. **A consumer reuses it by tag.** `pip install "git+…@v3.15.0-SNAPSHOT"`, or run the
   bundled example — see [Use it](#use-it).

The whole story demonstrates feasibility for Gerrit issue
[40011133](https://issues.gerritcodereview.com/issues/40011133) ("Consider using
Swagger from OpenApi for REST API").

## Version

Generated from **Gerrit 3.15.0-SNAPSHOT** and tagged **`v3.15.0-SNAPSHOT`** — the tag
mirrors the Gerrit version. The *package* version is `3.15.0.dev0`: PEP 440 forbids a
`-SNAPSHOT` suffix, so the pre-release is expressed as `.dev0` while the git tag keeps
the Gerrit label.

## What's in this repo

- `gerrit_client/` — the generated package: **325 operations** across **8 API classes**
  (`api/`) and **275 pydantic models** (`models/`), over `urllib3`.
- `gerrit_xssi/` — a hand-written `GerritApiClient(ApiClient)` subclass that strips
  Gerrit's `)]}'` XSSI guard before deserialization (the one Gerrit-specific step; see
  below). It lives outside the generated package, so regeneration never touches it.
- `examples/get-change-detail/` — a runnable example: an anonymous `GET /changes/{id}`
  rendered as a colored, Web-UI-style summary using Gerrit's own palette.
- `rest-api-openapi.json`, `generate.sh` — the pinned spec and the generation script.

## Regenerate

```bash
./generate.sh [path-or-url]      # default: ./rest-api-openapi.json
```

The package version is derived from the spec's `info.version` (converted to PEP 440).
Pass a URL to refetch the spec from a running Gerrit first.

## The Gerrit-specific handling

The spec is consumed as-is, and **no generated code is patched**:

1. **XSSI guard** — every Gerrit JSON body starts with `)]}'` on its own line, which is
   not valid JSON and not expressible in OpenAPI. `gerrit_xssi.GerritApiClient` subclasses
   the generated `ApiClient` and strips it in `deserialize` — the single injection point.
   (The Rust SDK cannot do this — blocking reqwest has no such hook — but Python's client
   does, so no source edits are needed here.)

The case-colliding `O`/`o` query params and the enum constants are handled correctly by
the python generator on their own, so — unlike the Rust and Go SDKs respectively — no
query patch and no enum-prefix flag are needed.

## Build & test

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'      # editable install of gerrit_client + gerrit_xssi
pytest                       # unit tests (gerrit_xssi strip)
```

## Use it

### Run the example — local, no publish needed

From a clone, against a live Gerrit (uses the local package):

```bash
pip install -e .
python examples/get-change-detail/main.py --change 622261
```

### From GitHub — after publishing

`pip install` the SDK straight from the tag, in your own project or a throwaway venv:

```bash
pip install "git+https://github.com/davido/gerrit-sdk-python@v3.15.0-SNAPSHOT"
```

```python
from gerrit_client.api.changes_api import ChangesApi
from gerrit_client.configuration import Configuration
from gerrit_xssi import GerritApiClient

config = Configuration(host="https://gerrit-review.googlesource.com")
api = ChangesApi(GerritApiClient(config))   # GerritApiClient strips the )]}' guard
change = api.get_changes_change_id("621763", o2=["LABELS", "CURRENT_REVISION"])
print(change.subject)
```

Python has no crates.io/tag-native install like Cargo, and no `/vN` module rule like Go
— reuse is `pip install "git+…@<tag>"`, so the git tag is the version contract.

## License

Apache 2.0. See [LICENSE.txt](LICENSE.txt).
