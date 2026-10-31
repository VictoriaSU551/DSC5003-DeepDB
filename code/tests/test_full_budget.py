import subprocess
import sys
from pathlib import Path


def test_cli_accepts_fractional_paper_budget(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'maqp.py'
    process = subprocess.run([sys.executable, str(script), '--ensemble_budget_factor', '0.5'],
                             cwd=str(tmp_path), capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
