#!/usr/bin/env python3
"""
patch_workspace_cm.py

Reads a full K8s ConfigMap manifest from `workspace.yaml`, locates the
literal block under `data["workspace.yaml"]`, and either adds or removes
the specified grpc_server entry based on --action, --host, --port, and
--location-name arguments.
"""

import sys
import re
import argparse
from io import StringIO
from pathlib import Path
from ruamel.yaml import YAML

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
FILE = Path("workspace.yaml")
# ────────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Add or remove a grpc_server entry in a workspace.yaml ConfigMap"
    )
    p.add_argument(
        "--action",
        choices=["add", "remove"],
        default="add",
        help="add (default) will insert if missing; remove will delete if present",
    )
    p.add_argument(
        "--host",
        required=True,
        help="The grpc_server host to add/remove",
    )
    p.add_argument(
        "--port",
        type=int,
        required=True,
        help="The grpc_server port to add/remove",
    )
    p.add_argument(
        "--location-name",
        dest="location_name",
        required=True,
        help="The grpc_server location_name to add/remove",
    )
    return p.parse_args()

def read_lines():
    return FILE.read_text(encoding="utf-8").splitlines(keepends=True)

def write_lines(lines):
    FILE.write_text("".join(lines), encoding="utf-8")

def find_block(lines):
    pat = re.compile(r'^(\s*)workspace\.yaml:\s*\|-\s*$')
    for i, line in enumerate(lines):
        m = pat.match(line)
        if m:
            indent = len(m.group(1)) + 2
            for j in range(i+1, len(lines)):
                if lines[j].strip() == "":
                    continue
                lead = len(lines[j]) - len(lines[j].lstrip(" "))
                if lead < indent:
                    return i, j, indent
            return i, len(lines), indent
    sys.exit("❌ Could not locate `workspace.yaml: |-` block in manifest.")

def extract_yaml(lines, start, end, indent):
    buf = []
    for L in lines[start+1:end]:
        buf.append(L[indent:] if len(L) > indent else "")
    return "".join(buf)

def dump_yaml_block(obj, indent):
    y = YAML()
    y.width = 4096
    buf = StringIO()
    y.dump(obj, buf)
    out = []
    for l in buf.getvalue().splitlines(keepends=True):
        out.append(" " * indent + l)
    return out

def main():
    args = parse_args()

    # Build the target block from arguments
    target = {
        "grpc_server": {
            "host": args.host,
            "port": args.port,
            "location_name": args.location_name,
        }
    }

    lines = read_lines()
    start, end, indent = find_block(lines)

    raw = extract_yaml(lines, start, end, indent)
    yaml = YAML()
    inner = yaml.load(StringIO(raw)) or {}
    if not isinstance(inner, dict):
        inner = {}

    lf = inner.get("load_from")
    if not isinstance(lf, list):
        lf = []

    def is_target(e):
        gs = e.get("grpc_server", {})
        return (
            gs.get("host") == target["grpc_server"]["host"]
            and gs.get("location_name") == target["grpc_server"]["location_name"]
        )

    modified = False

    if args.action == "add":
        if any(is_target(e) for e in lf):
            print("✅ Entry already exists; nothing to do.")
        else:
            lf.append(target)
            modified = True
            print("➕ Appended grpc_server entry.")
    else:  # remove
        new_lf = [e for e in lf if not is_target(e)]
        if len(new_lf) == len(lf):
            print("✅ Entry not found; nothing to remove.")
        else:
            lf = new_lf
            modified = True
            print("➖ Removed grpc_server entry.")

    if modified:
        inner["load_from"] = lf
        new_block = dump_yaml_block(inner, indent)
        updated = lines[: start+1] + new_block + lines[end:]
        write_lines(updated)
        print(f"✅ `{FILE}` updated in place. Now run `kubectl apply -f {FILE}`")

if __name__ == "__main__":
    main()
