#!/usr/bin/env python3
"""data-desk.py — local data workbench helper (SQLite store + DuckDB engine).

Cross-platform (macOS / Linux / Windows). Requires the DuckDB CLI.

Usage:
    python data-desk.py init <db-path>
    python data-desk.py import <db-path> <file> [file...]
    python data-desk.py tables <db-path>
    python data-desk.py query <db-path> "<SQL>"
    python data-desk.py convert <input-file> <output-file>
"""
import csv
import io
import os
import shutil
import subprocess
import sys

# --- locate duckdb CLI -------------------------------------------------------
FALLBACKS = [
    os.path.expanduser("~/.local/bin/duckdb"),
    "/usr/local/bin/duckdb",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\duckdb.exe"),
]


def find_duckdb():
    p = shutil.which("duckdb")
    if p:
        return p
    for f in FALLBACKS:
        if os.path.isfile(f) and os.access(f, os.X_OK):
            return f
    sys.exit("duckdb CLI not found; install via https://install.duckdb.org, brew, or winget")


DUCKDB = find_duckdb()

EXT_LOAD = "INSTALL sqlite; LOAD sqlite; INSTALL excel; LOAD excel;"


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def usage():
    print(__doc__.strip())
    sys.exit(1)


def resolve_path(p):
    return os.path.abspath(p)


def table_name(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in stem.lower())
    return out or "table"


def run_sql(sql, csv_output=False):
    cmd = [DUCKDB] + (["-csv"] if csv_output else []) + ["-noheader", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(r.stderr.strip() or "duckdb command failed")
    return r.stdout


def source_expr(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    p = path.replace("'", "''")
    if ext in ("csv", "tsv"):
        return f"read_csv('{p}', auto_detect = true)"
    if ext == "json":
        return f"read_json('{p}', format = 'array')"
    if ext in ("jsonl", "ndjson"):
        return f"read_json('{p}', format = 'newline_delimited')"
    if ext in ("parquet", "pq"):
        return f"'{p}'"
    if ext in ("xlsx", "xls"):
        return f"read_xlsx('{p}', header = true)"
    die(f"unsupported input extension: .{ext}")


def attach(db):
    d = db.replace("'", "''")
    return f"LOAD sqlite; ATTACH '{d}' AS db (TYPE sqlite); USE db;"


# --- subcommands --------------------------------------------------------------
def cmd_init(args):
    if len(args) < 1:
        usage()
    db = resolve_path(args[0])
    os.makedirs(os.path.dirname(db), exist_ok=True)
    run_sql(EXT_LOAD)  # pre-install extensions
    out = run_sql(f"{attach(db)} SELECT 'ok: {db}' AS status;")
    print(out.strip() or f"ok: {db}")


def cmd_import(args):
    if len(args) < 2:
        usage()
    db = resolve_path(args[0])
    os.makedirs(os.path.dirname(db), exist_ok=True)
    run_sql(EXT_LOAD)
    for f in args[1:]:
        fp = resolve_path(f)
        if not os.path.isfile(fp):
            die(f"file not found: {fp}")
        t = table_name(fp)
        src = source_expr(fp)
        out = run_sql(
            f"{attach(db)} CREATE OR REPLACE TABLE db.\"{t}\" AS SELECT * FROM {src};"
            f" SELECT '{t}' AS table, count() AS rows FROM db.\"{t}\";",
            csv_output=True,
        )
        print(out.strip())


def cmd_tables(args):
    if len(args) < 1:
        usage()
    db = resolve_path(args[0])
    run_sql(EXT_LOAD)
    listing = run_sql(f"{attach(db)} SELECT table_name FROM duckdb_tables() WHERE database_name = 'db' ORDER BY 1;", csv_output=True)
    names = [r[0] for r in csv.reader(io.StringIO(listing)) if r]
    if not names:
        return
    w = max(len(n) for n in names)
    print(f"table_name{' ' * (w - 10)},rows" if w > 10 else "table_name,rows")
    for n in names:
        out = run_sql(f"{attach(db)} SELECT count() FROM db.\"{n}\";", csv_output=True).strip()
        print(f"{n},{out}")


def cmd_query(args):
    if len(args) < 2:
        usage()
    db = resolve_path(args[0])
    run_sql(EXT_LOAD)
    sql = args[1]
    header = ["-csv"] if not sql.lower().lstrip().startswith("copy") else []
    cmd = [DUCKDB] + header + ["-c", f"{attach(db)} {sql}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(r.stderr.strip() or "duckdb command failed")
    sys.stdout.write(r.stdout)


def cmd_convert(args):
    if len(args) < 2:
        usage()
    src, dst = resolve_path(args[0]), resolve_path(args[1])
    if src == dst:
        die("refusing: input and output are the same file")
    ext = os.path.splitext(dst)[1].lower().lstrip(".")
    clauses = {
        "parquet": "", "pq": "",
        "csv": "(FORMAT csv, HEADER)",
        "tsv": "(FORMAT csv, HEADER, DELIMITER '\\t')",
        "json": "(FORMAT json, ARRAY true)",
        "jsonl": "(FORMAT json, ARRAY false)",
        "ndjson": "(FORMAT json, ARRAY false)",
        "xlsx": "(FORMAT xlsx)",
    }
    if ext not in clauses:
        die(f"unsupported output extension: .{ext}")
    run_sql(EXT_LOAD)
    s, d = src.replace("'", "''"), dst.replace("'", "''")
    run_sql(f"COPY (SELECT * FROM {source_expr(src)}) TO '{d}' {clauses[ext]};")
    print(f"converted: {src} -> {dst}")


COMMANDS = {"init": cmd_init, "import": cmd_import, "tables": cmd_tables,
            "query": cmd_query, "convert": cmd_convert}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        usage()
    COMMANDS[sys.argv[1]](sys.argv[2:])
