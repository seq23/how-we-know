"""An idle batch sends restored renders through captions before shelving."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
source = (root / "bin/batch-session.sh").read_text()
idle = source.split("phase_idle() {", 1)[1].split("\n}\n", 1)[0]
# Execute the real idle branch with inert stages: never source the batch,
# invoke its publishing functions, or require live media.
def exercise(body):
    script = '''
pending_audio=''; pending_render=''; pending_plan=''
step() { echo "stage:$1:$2"; }
phase_idle() {
''' + body + '\n}\nphase_idle\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines() if line.startswith("stage:")]

expected = ["stage:captions:phase_captions", "stage:shelve:shelve_shorts",
            "stage:harvest:harvest_footage"]
assert exercise(idle) == expected
# Negative proof: restoring the former idle branch loses the caption stage.
assert exercise(idle.replace("  step captions phase_captions\n", "")) != expected
print("idle batch captions: ok (including negative proof)")
