r"""
regenerate_requirements.py

Single entry point that regenerates the full requirements database from the
DSF source files in the correct dependency order:

  1. generate_rxml_requirements  -- DSF  --> packageRxml/*.rxml + manifest
  2. generate_dsi_elements       -- rxml --> DSI rxml + ixml entries

Run from the project root with:
    venv\Scripts\python.exe tools\regenerate_requirements.py
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

print("=" * 60)
print("Step 1/2: generate_rxml_requirements")
print("=" * 60)
import generate_rxml_requirements
generate_rxml_requirements.main()

print()
print("=" * 60)
print("Step 2/2: generate_dsi_elements")
print("=" * 60)
import generate_dsi_elements
generate_dsi_elements.generate()
