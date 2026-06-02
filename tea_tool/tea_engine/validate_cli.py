"""CLI: validate experiment YAML(s) and print the completeness report.

    python -m tea_engine.validate_cli experiments/paper_oh_2026_pet_pma.yaml
    python -m tea_engine.validate_cli experiments/        # whole folder

Exit code 1 if any file has ERRORS (schema_version>=2 files are strict).
"""
import sys
import io
from pathlib import Path

import yaml

from .schema_validate import validate_experiment

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _iter_paths(args):
    if not args:
        args = ["experiments"]
    for a in args:
        p = Path(a)
        if p.is_dir():
            yield from sorted(q for q in p.glob("*.yaml") if not q.name.startswith("_"))
        elif p.exists():
            yield p


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    any_err = False
    n = 0
    for p in _iter_paths(argv):
        n += 1
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            print(f"[{p.name}] YAML parse error: {e}")
            any_err = True
            continue
        rep = validate_experiment(raw)
        print(rep.to_text())
        print()
        any_err = any_err or bool(rep.errors)
    print(f"Validated {n} file(s). {'ERRORS present' if any_err else 'no blocking errors'}.")
    return 1 if any_err else 0


if __name__ == "__main__":
    sys.exit(main())
