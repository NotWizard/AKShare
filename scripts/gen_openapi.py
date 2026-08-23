#!/usr/bin/env python3
"""Regenerate ``shared/openapi.json`` from the LIVE FastAPI app (G16 · O-H7).

The committed schema is what the frontend codegen (``npm run gen:api``) and any
external consumer read. It drifts silently whenever a route/model changes — the
committed copy was missing every ``/crcl/*`` route and G08's ``/api/v1/session``
+ POST/GET refresh split. ``backend/tests/test_openapi_drift.py`` fails when this
file is out of sync with the app, and this script is how you bring it back in
sync:

    .venv312/bin/python scripts/gen_openapi.py

Dumped with ``indent=2, ensure_ascii=False`` so the Chinese summaries stay
readable and the diff is line-oriented.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app  # noqa: E402

OUT = PROJECT_ROOT / "shared" / "openapi.json"


def main():
    schema = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"✅ wrote {OUT.relative_to(PROJECT_ROOT)} "
          f"({len(schema['paths'])} paths, version {schema['info']['version']})")


if __name__ == "__main__":
    main()
