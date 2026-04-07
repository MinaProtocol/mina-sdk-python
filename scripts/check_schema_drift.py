#!/usr/bin/env python3
"""Check for schema drift between the local GraphQL schema and a live Mina node.

Usage:
    python scripts/check_schema_drift.py --endpoint http://localhost:8080/graphql [--strict]

Exit codes:
    0 - schemas match
    1 - schemas differ (only in --strict mode)
    2 - connection/introspection error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "src" / "mina_sdk" / "schema" / "graphql_schema.json"

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


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a schema for stable comparison by sorting all lists deterministically."""
    data = schema.get("data", schema)
    s = data.get("__schema", data)

    types_list = sorted(s.get("types", []), key=lambda t: t.get("name", ""))
    normalized_types = []
    for t in types_list:
        nt = dict(t)
        if nt.get("fields"):
            nt["fields"] = sorted(nt["fields"], key=lambda f: f.get("name", ""))
            for field in nt["fields"]:
                if field.get("args"):
                    field["args"] = sorted(field["args"], key=lambda a: a.get("name", ""))
        if nt.get("inputFields"):
            nt["inputFields"] = sorted(nt["inputFields"], key=lambda f: f.get("name", ""))
        if nt.get("enumValues"):
            nt["enumValues"] = sorted(nt["enumValues"], key=lambda e: e.get("name", ""))
        if nt.get("interfaces"):
            nt["interfaces"] = sorted(nt["interfaces"], key=lambda i: i.get("name", ""))
        if nt.get("possibleTypes"):
            nt["possibleTypes"] = sorted(nt["possibleTypes"], key=lambda p: p.get("name", ""))
        normalized_types.append(nt)

    return {
        "queryType": s.get("queryType"),
        "mutationType": s.get("mutationType"),
        "subscriptionType": s.get("subscriptionType"),
        "types": normalized_types,
    }


def compute_diff(local: dict[str, Any], remote: dict[str, Any]) -> list[str]:
    """Compute human-readable differences between two normalized schemas."""
    diffs: list[str] = []

    local_types = {t["name"]: t for t in local["types"]}
    remote_types = {t["name"]: t for t in remote["types"]}

    local_names = set(local_types.keys())
    remote_names = set(remote_types.keys())

    for name in sorted(local_names - remote_names):
        diffs.append(f"  REMOVED type: {name}")
    for name in sorted(remote_names - local_names):
        diffs.append(f"  ADDED type: {name}")

    for name in sorted(local_names & remote_names):
        lt = local_types[name]
        rt = remote_types[name]

        if lt.get("kind") != rt.get("kind"):
            diffs.append(f"  CHANGED {name}: kind {lt.get('kind')} -> {rt.get('kind')}")

        # Compare fields
        local_fields = {f["name"]: f for f in (lt.get("fields") or [])}
        remote_fields = {f["name"]: f for f in (rt.get("fields") or [])}
        for fname in sorted(set(local_fields) - set(remote_fields)):
            diffs.append(f"  REMOVED field: {name}.{fname}")
        for fname in sorted(set(remote_fields) - set(local_fields)):
            diffs.append(f"  ADDED field: {name}.{fname}")
        for fname in sorted(set(local_fields) & set(remote_fields)):
            lf = local_fields[fname]
            rf = remote_fields[fname]
            if lf.get("type") != rf.get("type"):
                diffs.append(f"  CHANGED field type: {name}.{fname}")
            # Compare args
            local_args = {a["name"]: a for a in (lf.get("args") or [])}
            remote_args = {a["name"]: a for a in (rf.get("args") or [])}
            for aname in sorted(set(local_args) - set(remote_args)):
                diffs.append(f"  REMOVED arg: {name}.{fname}({aname})")
            for aname in sorted(set(remote_args) - set(local_args)):
                diffs.append(f"  ADDED arg: {name}.{fname}({aname})")

        # Compare inputFields
        local_inputs = {f["name"]: f for f in (lt.get("inputFields") or [])}
        remote_inputs = {f["name"]: f for f in (rt.get("inputFields") or [])}
        for fname in sorted(set(local_inputs) - set(remote_inputs)):
            diffs.append(f"  REMOVED inputField: {name}.{fname}")
        for fname in sorted(set(remote_inputs) - set(local_inputs)):
            diffs.append(f"  ADDED inputField: {name}.{fname}")

        # Compare enumValues
        local_enums = {e["name"] for e in (lt.get("enumValues") or [])}
        remote_enums = {e["name"] for e in (rt.get("enumValues") or [])}
        for ename in sorted(local_enums - remote_enums):
            diffs.append(f"  REMOVED enumValue: {name}.{ename}")
        for ename in sorted(remote_enums - local_enums):
            diffs.append(f"  ADDED enumValue: {name}.{ename}")

    return diffs


def fetch_remote_schema(endpoint: str, timeout: float = 60.0) -> dict[str, Any]:
    """Fetch schema via introspection query from a live Mina node."""
    resp = httpx.post(
        endpoint,
        json={"query": INTROSPECTION_QUERY},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check GraphQL schema drift against a Mina node")
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/graphql",
        help="Mina node GraphQL endpoint (default: http://127.0.0.1:8080/graphql)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 on schema differences (default: warn only)",
    )
    parser.add_argument(
        "--branch",
        default="unknown",
        help="Branch label for log messages (e.g. master, compatible, develop)",
    )
    args = parser.parse_args()

    # Load local schema
    try:
        local_raw = json.loads(SCHEMA_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: Cannot load local schema from {SCHEMA_PATH}: {e}", file=sys.stderr)
        return 2

    # Fetch remote schema
    try:
        print(f"Fetching schema from {args.endpoint} (branch: {args.branch})...")
        remote_raw = fetch_remote_schema(args.endpoint)
    except (httpx.HTTPError, Exception) as e:
        print(f"ERROR: Cannot fetch remote schema: {e}", file=sys.stderr)
        return 2

    # Normalize and compare
    local_norm = normalize_schema(local_raw)
    remote_norm = normalize_schema(remote_raw)

    if local_norm == remote_norm:
        print(f"OK: Local schema matches {args.branch} node schema.")
        return 0

    diffs = compute_diff(local_norm, remote_norm)
    level = "ERROR" if args.strict else "WARNING"

    print(f"\n{level}: Schema drift detected against {args.branch} ({len(diffs)} difference(s)):\n")
    for d in diffs:
        print(d)
    print()

    if args.strict:
        print("FAIL: Schema is out of sync with the node. Update src/mina_sdk/schema/graphql_schema.json")
        return 1
    else:
        print(f"WARN: Schema differs from {args.branch} (non-blocking).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
