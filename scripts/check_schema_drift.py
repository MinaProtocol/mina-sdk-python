#!/usr/bin/env python3
"""Check for schema drift between the SDK and a live Mina node, in two layers:

  1. Introspection diff: compare ``src/mina_sdk/schema/graphql_schema.json``
     to the live ``__schema`` returned by the daemon.
  2. Live query check: parse ``src/mina_sdk/daemon/queries.py``, send each
     operation with sentinel variables, and classify GraphQL errors as
     either schema drift (parse/validation) or runtime (auth, value-validation).

Designed for a lightnet-style local daemon (see
``.github/workflows/schema-drift.yml`` for the CI setup); do not point at a
public node by default.

Usage:
    python scripts/check_schema_drift.py --endpoint http://localhost:8080/graphql [--strict]

Exit codes:
    0 - no drift (or non-strict mode)
    1 - drift detected in --strict mode
    2 - connection / introspection error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "src" / "mina_sdk" / "schema" / "graphql_schema.json"
QUERIES_PATH = REPO_ROOT / "src" / "mina_sdk" / "daemon" / "queries.py"

# Sentinel addresses — syntactically valid B62q keys. The daemon may not have
# the corresponding accounts, but the schema layer will still validate.
SENTINEL_SENDER = "B62qpRzFVjd56FiHnNfxokVbcHMQLT119My1FEdSq8ss7KomLiSZcan"
SENTINEL_RECEIVER = "B62qrPN5Y5yq8kGE3FbVKbGTdTAJNdtNtB5sNVpxyRwWGcDEhpMzc8g"

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          type {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
                ofType {
                  kind
                  name
                }
              }
            }
          }
          defaultValue
        }
        type {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
        isDeprecated
        deprecationReason
      }
      inputFields {
        name
        description
        type {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
        defaultValue
      }
      interfaces {
        kind
        name
        ofType {
          kind
          name
        }
      }
      enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
        deprecationReason
      }
      possibleTypes {
        kind
        name
      }
    }
  }
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: introspection diff
# ─────────────────────────────────────────────────────────────────────────────


def _name_of(item: Any) -> str:
    """Safe name extractor — returns '' for non-dict / missing-name entries
    so sorting never panics on `null` entries in introspection arrays."""
    if isinstance(item, dict):
        n = item.get("name")
        if isinstance(n, str):
            return n
    return ""


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a schema for stable comparison. Raises ValueError if the
    response is an error envelope without data.__schema, instead of silently
    returning a fake empty schema."""
    data = schema.get("data") if isinstance(schema.get("data"), dict) else schema
    sc = data.get("__schema") if isinstance(data, dict) else None
    if not isinstance(sc, dict):
        if schema.get("errors"):
            raise ValueError(
                f"introspection returned errors envelope (no data.__schema): {schema['errors']}"
            )
        raise ValueError("introspection response missing data.__schema")
    s = sc
    types_raw = s.get("types")
    if not isinstance(types_raw, list):
        raise ValueError(f"introspection __schema.types is not a list (got {type(types_raw).__name__})")

    types_list = sorted(types_raw, key=_name_of)
    normalized_types = []
    for t in types_list:
        if not isinstance(t, dict):
            continue
        nt = dict(t)
        if nt.get("fields"):
            nt["fields"] = sorted(nt["fields"], key=_name_of)
            for field in nt["fields"]:
                if isinstance(field, dict) and field.get("args"):
                    field["args"] = sorted(field["args"], key=_name_of)
        if nt.get("inputFields"):
            nt["inputFields"] = sorted(nt["inputFields"], key=_name_of)
        if nt.get("enumValues"):
            nt["enumValues"] = sorted(nt["enumValues"], key=_name_of)
        if nt.get("interfaces"):
            nt["interfaces"] = sorted(nt["interfaces"], key=_name_of)
        if nt.get("possibleTypes"):
            nt["possibleTypes"] = sorted(nt["possibleTypes"], key=_name_of)
        normalized_types.append(nt)

    return {
        "queryType": s.get("queryType"),
        "mutationType": s.get("mutationType"),
        "subscriptionType": s.get("subscriptionType"),
        "types": normalized_types,
    }


def compute_schema_diff(local: dict[str, Any], remote: dict[str, Any]) -> list[str]:
    """Compute human-readable differences between two normalized schemas."""
    diffs: list[str] = []

    local_types = {t["name"]: t for t in local["types"]}
    remote_types = {t["name"]: t for t in remote["types"]}

    for name in sorted(set(local_types) - set(remote_types)):
        diffs.append(f"REMOVED type: {name}")
    for name in sorted(set(remote_types) - set(local_types)):
        diffs.append(f"ADDED type: {name}")

    for name in sorted(set(local_types) & set(remote_types)):
        lt = local_types[name]
        rt = remote_types[name]
        # Only flag kind change when both sides set it — otherwise a partial
        # local dump emits a spurious "<None> -> OBJECT" per type.
        if lt.get("kind") is not None and rt.get("kind") is not None and lt["kind"] != rt["kind"]:
            diffs.append(f"CHANGED {name}: kind {lt['kind']} -> {rt['kind']}")

        local_fields = {f["name"]: f for f in (lt.get("fields") or [])}
        remote_fields = {f["name"]: f for f in (rt.get("fields") or [])}
        for fname in sorted(set(local_fields) - set(remote_fields)):
            diffs.append(f"REMOVED field: {name}.{fname}")
        for fname in sorted(set(remote_fields) - set(local_fields)):
            diffs.append(f"ADDED field: {name}.{fname}")
        for fname in sorted(set(local_fields) & set(remote_fields)):
            lf = local_fields[fname]
            rf = remote_fields[fname]
            if lf.get("type") != rf.get("type"):
                diffs.append(f"CHANGED field type: {name}.{fname}")
            local_args = {a["name"]: a for a in (lf.get("args") or [])}
            remote_args = {a["name"]: a for a in (rf.get("args") or [])}
            for aname in sorted(set(local_args) - set(remote_args)):
                diffs.append(f"REMOVED arg: {name}.{fname}({aname})")
            for aname in sorted(set(remote_args) - set(local_args)):
                diffs.append(f"ADDED arg: {name}.{fname}({aname})")
            # Compare arg types for shared keys — a scalar swap like
            # account(token: UInt64 -> TokenId) is invisible without this.
            for aname in sorted(set(local_args) & set(remote_args)):
                if local_args[aname].get("type") != remote_args[aname].get("type"):
                    diffs.append(f"CHANGED arg type: {name}.{fname}({aname})")

        local_inputs = {f["name"]: f for f in (lt.get("inputFields") or [])}
        remote_inputs = {f["name"]: f for f in (rt.get("inputFields") or [])}
        for fname in sorted(set(local_inputs) - set(remote_inputs)):
            diffs.append(f"REMOVED inputField: {name}.{fname}")
        for fname in sorted(set(remote_inputs) - set(local_inputs)):
            diffs.append(f"ADDED inputField: {name}.{fname}")
        # Compare inputField types for shared keys.
        for fname in sorted(set(local_inputs) & set(remote_inputs)):
            if local_inputs[fname].get("type") != remote_inputs[fname].get("type"):
                diffs.append(f"CHANGED inputField type: {name}.{fname}")

        local_enums = {e["name"] for e in (lt.get("enumValues") or [])}
        remote_enums = {e["name"] for e in (rt.get("enumValues") or [])}
        for ename in sorted(local_enums - remote_enums):
            diffs.append(f"REMOVED enumValue: {name}.{ename}")
        for ename in sorted(remote_enums - local_enums):
            diffs.append(f"ADDED enumValue: {name}.{ename}")

    return diffs


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2: live query check
# ─────────────────────────────────────────────────────────────────────────────


_OP_RE = re.compile(r'^(\w+)\s*=\s*"""(.*?)"""', re.MULTILINE | re.DOTALL)
# Anchor at the start of the body — without ^, varsRe could bind to inner
# field-arg parens like `bestChain(maxLength: 1)`.
_VARS_RE = re.compile(r"^\s*(?:query|mutation|subscription)(?:\s+\w+)?\s*\(([^)]*)\)", re.DOTALL)
_DECL_RE = re.compile(r"^\$(\w+)\s*:\s*([\w!\[\]]+)")
_OPERATION_START_RE = re.compile(r"^\s*(query|mutation|subscription)\b", re.IGNORECASE)


def parse_queries(src: str) -> list[tuple[str, str]]:
    """Extract NAME = \"\"\"...\"\"\" pairs whose body is an actual GraphQL
    operation. Filters out unrelated triple-quoted constants in the module."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _OP_RE.finditer(src):
        name, body = m.group(1), m.group(2)
        if name in seen:
            continue
        if not _OPERATION_START_RE.match(body):
            continue
        seen.add(name)
        out.append((name, body))
    return out


def parse_variable_decls(body: str) -> list[tuple[str, str]]:
    """Pull ($var: Type[!], ...) out of an operation header."""
    m = _VARS_RE.search(body)
    if not m:
        return []
    decls: list[tuple[str, str]] = []
    for raw in m.group(1).split(","):
        raw = raw.strip()
        if not raw:
            continue
        d = _DECL_RE.match(raw)
        if d:
            decls.append((d.group(1), d.group(2)))
    return decls


def sentinel_for_type(type_name: str) -> Any:
    base = re.sub(r"[\[\]!]", "", type_name)
    return {
        "PublicKey": SENTINEL_SENDER,
        "UInt32": "1000000000",
        "UInt64": "1000000000",
        "Fee": "1000000000",
        "Balance": "1000000000",
        "Int": 1,
        "String": "1",
        "TokenId": "1",
        "Boolean": True,
        "SendPaymentInput": {
            "from": SENTINEL_SENDER,
            "to": SENTINEL_RECEIVER,
            "amount": "1000000000",
            "fee": "1000000000",
        },
        "SendDelegationInput": {
            "from": SENTINEL_SENDER,
            "to": SENTINEL_RECEIVER,
            "fee": "1000000000",
        },
        "SetSnarkWorkerInput": {"publicKey": SENTINEL_SENDER},
        "SetSnarkWorkFee": {"fee": "1000000000"},
    }.get(base, None)


def build_variables(decls: list[tuple[str, str]]) -> dict[str, Any] | None:
    vars: dict[str, Any] = {}
    for name, typ in decls:
        v = sentinel_for_type(typ)
        if v is None:
            return None
        vars[name] = v
    return vars


# Case-insensitive substrings that uniquely identify schema-level errors
# emitted by Mina's GraphQL surface (graphql-ppx / OCaml). We deliberately
# omit bare "expected type" because it appears in both real drift and in
# value-coercion runtime errors ("Expected type Foo, found Bar"); the
# `_VALUE_COERCION_RE` below catches the runtime variant explicitly.
_DRIFT_PATTERNS = (
    "cannot query field",
    "unknown argument",
    "unknown type",
    "is not defined",
    "is not a subtype",
    "is required",
    "but not provided",
    "used in position expecting type",
    "must have a sub selection",
    "did you mean",
    "unknown directive",
)

# Matches Mina's "Argument X of type Y expected on field Z, found <value>"
# — value validation, not schema drift.
_VALUE_COERCION_RE = re.compile(r"expected on field .* found ", re.IGNORECASE)


def classify_error(err: dict[str, Any]) -> str:
    """Decide whether a GraphQL error reflects schema drift or runtime
    failure. Message-pattern match takes priority over `path` — Mina attaches
    `path` to many validation errors, so a path-first short-circuit silently
    drops real drift to the runtime bucket."""
    msg = err.get("message") or ""
    lc = msg.lower()
    if any(p in lc for p in _DRIFT_PATTERNS):
        return "drift"
    if _VALUE_COERCION_RE.search(msg):
        return "runtime"
    if err.get("path"):
        return "runtime"
    # Unknown error shape — surface as drift so silent breakage is visible
    # in --strict mode at least.
    return "drift"


_http_client = httpx.Client(timeout=30.0)


def post_graphql(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = _http_client.post(endpoint, json=payload)
    if resp.status_code < 200 or resp.status_code >= 300:
        snippet = resp.text
        if len(snippet) > 200:
            snippet = snippet[:200] + "…"
        raise RuntimeError(f"HTTP {resp.status_code} {resp.reason_phrase}: {snippet}")
    return resp.json()


@dataclass
class QueryStats:
    ok: int = 0
    runtime: int = 0
    drift: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # coverage gaps (stale sentinel table)
    failures: list[str] = field(default_factory=list)  # infra (HTTP / network / parse)


def _missing_sentinel_types(decls: list[tuple[str, str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for _, typ in decls:
        if sentinel_for_type(typ) is None and typ not in seen:
            seen.add(typ)
            out.append(typ)
    return out


def run_query_layer(endpoint: str) -> QueryStats:
    stats = QueryStats()
    try:
        src = QUERIES_PATH.read_text()
    except OSError as e:
        print(f"FAIL: cannot read queries module: {e}")
        stats.failures.append(f"read queries module: {e}")
        return stats
    ops = parse_queries(src)
    if not ops:
        print("WARN: no operations parsed from queries module")
        stats.failures.append("no operations parsed from queries module")
        return stats

    for name, body in ops:
        decls = parse_variable_decls(body)
        vars_ = build_variables(decls)
        if vars_ is None:
            missing = _missing_sentinel_types(decls)
            print(f"SKIP  {name} (no sentinel for: {', '.join(missing)})")
            stats.skipped.append(f"{name}: missing sentinel for {', '.join(missing)}")
            continue

        try:
            result = post_graphql(endpoint, {"query": body, "variables": vars_})
        except (httpx.HTTPError, RuntimeError, ValueError) as e:
            print(f"FAIL  {name}: {e}")
            stats.failures.append(f"{name}: {e}")
            continue

        errors = result.get("errors") or []
        if not errors:
            print(f"OK    {name}")
            stats.ok += 1
            continue

        classified = [(classify_error(e), e) for e in errors]
        drift_errs = [e for kind, e in classified if kind == "drift"]
        if drift_errs:
            msgs = "; ".join(e.get("message", "") for e in drift_errs)
            print(f"DRIFT {name}: {msgs}")
            stats.drift.append(f"{name}: {msgs}")
        else:
            msgs = "; ".join(e.get("message", "") for _, e in classified)
            print(f"RUNTIME {name}: {msgs}")
            stats.runtime += 1

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Check GraphQL schema drift against a Mina node")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080/graphql")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--branch", default="unknown")
    parser.add_argument("--skip-schema", action="store_true")
    parser.add_argument("--skip-queries", action="store_true")
    args = parser.parse_args()

    schema_diff: list[str] = []

    if not args.skip_schema:
        print(f"\n── Layer 1: schema introspection ({args.branch}) ──")
        try:
            local_raw = json.loads(SCHEMA_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"ERROR: Cannot load local schema from {SCHEMA_PATH}: {e}", file=sys.stderr)
            return 2

        try:
            print(f"Fetching introspection from {args.endpoint}...")
            remote_raw = post_graphql(args.endpoint, {"query": INTROSPECTION_QUERY})
        except (httpx.HTTPError, RuntimeError, ValueError) as e:
            print(f"ERROR: Cannot fetch remote schema: {e}", file=sys.stderr)
            return 2

        try:
            local = normalize_schema(local_raw)
            remote = normalize_schema(remote_raw)
        except ValueError as e:
            print(f"ERROR: malformed schema: {e}", file=sys.stderr)
            return 2

        schema_diff = compute_schema_diff(local, remote)
        if not schema_diff:
            print("OK: local schema matches node schema")
        else:
            print(f"Schema drift: {len(schema_diff)} difference(s)")
            for d in schema_diff:
                print(f"  {d}")

    qstats = QueryStats()
    if not args.skip_queries:
        print(f"\n── Layer 2: live query check ({args.branch}) ──")
        qstats = run_query_layer(args.endpoint)
        print(
            f"\nResults: {qstats.ok} ok, {len(qstats.drift)} drift, {qstats.runtime} runtime, "
            f"{len(qstats.skipped)} skipped, {len(qstats.failures)} infra-failures"
        )

    print(f"\n── Summary ({args.branch}) ──")
    if args.skip_schema:
        print("Schema diffs:   SKIPPED")
    else:
        print(f"Schema diffs:    {len(schema_diff)}")
    if args.skip_queries:
        print("Query drift:    SKIPPED")
    else:
        print(f"Query drift:     {len(qstats.drift)}")
        print(f"Skipped (cov):   {len(qstats.skipped)}")
        print(f"Infra failures:  {len(qstats.failures)}")

    # Infra failures always fail — we can't trust the result if we couldn't
    # talk to the daemon.
    if qstats.failures:
        print("FAIL: infrastructure errors prevented a clean check")
        return 1

    total_drift = len(schema_diff) + len(qstats.drift)
    if total_drift == 0 and not qstats.skipped:
        print("OK: no drift detected")
        return 0
    if args.strict:
        # In strict mode, skipped ops are also a failure: we can't claim the
        # SDK is in sync if we couldn't probe parts of it.
        print("FAIL: drift or coverage gap detected in --strict mode")
        return 1
    print(f"WARN: drift or coverage gap differs from {args.branch} (non-blocking).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
