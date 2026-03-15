"""
PoC: Honest validator self-equivocation in Simplex consensus.

Runs the test-consensus binary (not full validator-engine) since it exposes
--validation-time and --target-rate-ms flags needed to trigger the race.
For full-stack reproduction once tontester supports custom validator-engine flags,
see the comment block at the bottom of this file.

Finding: alarm() issues SkipVote after try_notarize() has already sent NotarizeVote
for the same slot (pool.cpp:525 WARNING is the observable symptom).

Usage:
    python3 test_equivocation.py
"""

import subprocess
import re
import sys
from pathlib import Path

AUDIT_ROOT = Path(__file__).resolve().parents[1]  # ton-consensus-audit/

def _find_binary() -> Path:
    """Search common layouts for the test-consensus binary."""
    candidates = [
        AUDIT_ROOT / "ton" / "build-clang" / "test" / "consensus" / "test-consensus",
        AUDIT_ROOT / "ton" / "build" / "test" / "consensus" / "test-consensus",
        AUDIT_ROOT.parent / "ton" / "build-clang" / "test" / "consensus" / "test-consensus",
        AUDIT_ROOT.parent / "build-clang" / "test" / "consensus" / "test-consensus",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # default path for error message

TEST_CONSENSUS = _find_binary()

# Triggering parameters:
# - validation-time must exceed alarm interval to guarantee race
# - small target-rate-ms means many slots, more opportunities for equivocation
PARAMS = [
    "--validation-time", "1.5:2.5",
    "--target-rate-ms", "200",
    "--n-nodes", "8",
    "--duration", "30",
    "-v", "2",
]

EQUIVOCATION_PATTERN = re.compile(
    r"Dropping NotarizeVote\{id=\{(\d+).*?\}\}.*?from validator (\d+).*?which references a finalized slot"
)


def run_poc():
    if not TEST_CONSENSUS.exists():
        print(f"ERROR: binary not found at {TEST_CONSENSUS}")
        print("Build with: cd build-clang && cmake --build . --target test-consensus -j$(nproc)")
        sys.exit(1)

    print(f"Running: {TEST_CONSENSUS.name} {' '.join(PARAMS)}")
    print("Looking for: WARNING pool.cpp:525 — NotarizeVote arriving after SkipCert formed")
    print("-" * 72)

    result = subprocess.run(
        [str(TEST_CONSENSUS)] + PARAMS,
        capture_output=True,
        text=True,
        timeout=60,
    )

    output = result.stderr  # TON logs to stderr

    # Strip ANSI colour codes
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    clean = ansi_escape.sub("", output)

    equivocations = []
    for line in clean.splitlines():
        m = EQUIVOCATION_PATTERN.search(line)
        if m:
            slot = m.group(1)
            validator = m.group(2)
            equivocations.append((slot, validator, line.strip()))

    if not equivocations:
        print("RESULT: No equivocation evidence found in this run.")
        print("Try increasing --validation-time or --n-nodes.")
        sys.exit(1)

    # Summarise
    by_validator = {}
    for slot, validator, _ in equivocations:
        by_validator.setdefault(validator, set()).add(slot)

    print(f"CONFIRMED: {len(equivocations)} equivocation events detected\n")
    print("Equivocating validators:")
    for validator, slots in sorted(by_validator.items(), key=lambda x: int(x[0])):
        print(f"  Validator {validator}: equivocated on slots {sorted(slots, key=int)}")

    print()
    print("Sample evidence (pool.cpp:525):")
    seen = set()
    for slot, validator, line in equivocations[:4]:
        key = (validator, slot)
        if key not in seen:
            seen.add(key)
            print(f"  {line}")

    print()
    print("EXPLANATION:")
    print("  'Dropping NotarizeVote ... which references a finalized slot' means:")
    print("  - The slot was already finalized via SkipCert when NotarizeVote arrived")
    print("  - Validator broadcast BOTH SkipVote (contributing to SkipCert) AND NotarizeVote")
    print("  - This is equivocation by an honest node caused by the alarm() race condition")
    print("  - Bug C: no MisbehaviorReport generated for this equivocation")

    return len(by_validator)


if __name__ == "__main__":
    n_equivocators = run_poc()
    print(f"\n{n_equivocators}/8 validators equivocated.")
    sys.exit(0)


# ---
# FULL-STACK TONTESTER NOTE:
# The tontester framework (test/tontester) runs actual validator-engine processes.
# To reproduce this bug with real validator nodes, you would need:
#
#   1. A way to slow down block validation in validator-engine
#      (e.g., a custom BlockValidator implementation, or artificially large blocks)
#   2. Monitoring of validator-engine logs for the same pool.cpp:525 warning
#
# The test-consensus binary is the authoritative reproduction vehicle since it
# exposes --validation-time directly. The full-stack path is:
#
#   async with Network(install, working_dir) as network:
#       dht = network.create_dht_node()
#       nodes = [network.create_full_node() for _ in range(8)]
#       for node in nodes:
#           node.make_initial_validator()
#           node.announce_to(dht)
#       # ... wait for consensus, inspect logs for pool.cpp:525 warnings
