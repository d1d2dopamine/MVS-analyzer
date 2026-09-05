#!/usr/bin/env python3
"""Synchronize readable helper code into existing Colab notebook forms; never executes them."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
helper=(root/"notebooks/mvs_colab.py").read_text().replace("from __future__ import annotations\n", "")
for path in (root/"notebooks").glob("*.ipynb"):
    book=json.loads(path.read_text())
    source="".join(book["cells"][0]["source"])
    start=source.index('"""MVS Colab runner.')
    finish=source.index("# A saved calibration is validated and reused.",start)
    book["cells"][0]["source"]=(source[:start]+helper+"\n"+source[finish:]).splitlines(True)
    book["metadata"].setdefault("colab",{})["private_outputs"]=True
    for cell in book["cells"]:cell["outputs"]=[];cell["execution_count"]=None
    path.write_text(json.dumps(book,ensure_ascii=False,indent=1)+"\n")
    print("Synchronized",path.name)
