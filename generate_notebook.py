"""
Stage 2 Notebook Generator & Headless Execution Script.
Builds and executes solution.ipynb with complete outputs, markdown narrative,
and analytical visualizations.
"""

from pathlib import Path
import nbformat as nbf
from nbclient import NotebookClient

BASE_DIR = Path(__file__).resolve().parent
NOTEBOOK_PATH = BASE_DIR / "solution.ipynb"


def regenerate_notebook():
    """Regenerate and re-execute solution.ipynb headlessly."""
    if not NOTEBOOK_PATH.exists():
        raise FileNotFoundError(f"Notebook template not found at {NOTEBOOK_PATH}")
    
    print(f"[REGENERATE] Loading {NOTEBOOK_PATH}...")
    nb = nbf.read(NOTEBOOK_PATH, as_version=4)
    client = NotebookClient(nb, timeout=600, kernel_name="python3")
    
    print("[EXECUTE] Running all cells headlessly...")
    client.execute(cwd=str(BASE_DIR))
    
    print(f"[SAVE] Persisting executed notebook to {NOTEBOOK_PATH}...")
    with open(NOTEBOOK_PATH, "w", encoding="utf-8") as f:
        nbf.write(nb, f)
    print("[SUCCESS] Notebook executed and saved with outputs!")


if __name__ == "__main__":
    regenerate_notebook()
