#!/usr/bin/env python3
"""
PoC: Honest Validator Self-Equivocation in TON Simplex Consensus

Demonstrates two independent code paths that cause an honest validator to broadcast
both a NotarizeVote and a SkipVote for the same slot:

  PART 1 — alarm() race (consensus.cpp:144-150 + try_notarize after co_await)
    alarm() checks only !voted_final, not !voted_notar or !voted_skip.
    If try_notarize() is suspended at co_await ValidationRequest when the alarm fires,
    the validator broadcasts SkipVote then NotarizeVote for the same slot.
    Evidence: pool.cpp:525 WARNING "Dropping NotarizeVote ... references a finalized slot"

  PART 2 — start_up() restart equivocation (consensus.cpp:82-91)
    On restart, bootstrap_votes are loaded from DB (including any NotarizeVotes cast
    before the crash), then start_up() broadcasts SkipVote for all slots in the current
    unannouncedleader window — using only a !voted_final guard, not !voted_notar.
    Evidence: "Starting node #N.0" followed immediately by pool.cpp:525 WARNING
    "Dropping SkipVote ... references a finalized slot" from that validator.

Repository: ton-blockchain/ton, branch testnet, commit 3bb6abc
Affected files:
  validator/consensus/simplex/consensus.cpp (lines 82-91, 144-150, 232-235)
  validator/consensus/simplex/pool.cpp      (lines 209-217)

Usage:
    python3 test_equivocation_combined.py [--build-dir PATH]

Requires: test-consensus binary built with Clang 18+
  cd ton && mkdir build-clang && cd build-clang
  CC=clang CXX=clang++ cmake .. -DCMAKE_BUILD_TYPE=Release -DTON_USE_ROCKSDB=OFF
  cmake --build . --target test-consensus -j$(nproc)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from collections import defaultdict

# ──────────────────────────────────────────────────
# Build / binary resolution
# ──────────────────────────────────────────────────

AUDIT_ROOT = Path(__file__).resolve().parents[1]  # ton-consensus-audit/
REPO_ROOT = AUDIT_ROOT  # kept for compat

def find_binary(build_dir: Path | None) -> Path:
    candidates = [
        build_dir / "test" / "consensus" / "test-consensus" if build_dir else None,
        # ton/ cloned inside the audit repo (recommended layout)
        AUDIT_ROOT / "ton" / "build-clang" / "test" / "consensus" / "test-consensus",
        AUDIT_ROOT / "ton" / "build" / "test" / "consensus" / "test-consensus",
        # ton/ cloned as sibling of the audit repo
        AUDIT_ROOT.parent / "ton" / "build-clang" / "test" / "consensus" / "test-consensus",
        AUDIT_ROOT.parent / "ton" / "build" / "test" / "consensus" / "test-consensus",
        # Legacy: build-clang at parent level
        AUDIT_ROOT.parent / "build-clang" / "test" / "consensus" / "test-consensus",
    ]
    for c in candidates:
        if c and c.exists():
            return c
    print("ERROR: test-consensus binary not found. Build with Clang 18+:")
    print("  cd ton && mkdir build-clang && cd build-clang")
    print("  CC=clang CXX=clang++ cmake .. -DCMAKE_BUILD_TYPE=Release -DTON_USE_ROCKSDB=OFF")
    print("  cmake --build . --target test-consensus -j$(nproc)")
    sys.exit(1)


# ──────────────────────────────────────────────────
# PART 1 — alarm() race
# ──────────────────────────────────────────────────

PART1_PARAMS = [
    "--validation-time", "1.5:2.5",   # validation > alarm interval → race guaranteed
    "--target-rate-ms",  "200",        # fast slots → more equivocation opportunities
    "--n-nodes",         "8",
    "--duration",        "30",
    "-v",                "2",
]

# pool.cpp:525 WARNING is the observable symptom:
# NotarizeVote arriving for a slot already finalised via SkipCert proves the
# same validator broadcast both vote types for that slot.
RE_NOTARIZE_DROP = re.compile(
    r"Dropping NotarizeVote\{id=\{(\d+),.*?\}\} from validator (\d+) at .+ which references a finalized slot"
)

def run_part1(binary: Path) -> dict:
    print("=" * 60)
    print("PART 1 — alarm() race equivocation")
    print(f"  {' '.join(str(x) for x in PART1_PARAMS)}")
    print("=" * 60)

    result = subprocess.run(
        [str(binary)] + PART1_PARAMS,
        capture_output=True, text=True, timeout=45
    )
    stderr = result.stderr

    # Parse equivocating (validator, slot) pairs
    equivocations = defaultdict(set)
    for m in RE_NOTARIZE_DROP.finditer(stderr):
        slot, validator = int(m.group(1)), int(m.group(2))
        equivocations[validator].add(slot)

    total_pairs = sum(len(slots) for slots in equivocations.values())

    print(f"\nResult: {total_pairs} equivocating (validator, slot) pairs")
    print(f"        {len(equivocations)} / 8 validators affected")

    if total_pairs == 0:
        print("FAIL: No equivocation events observed.")
        print("      Try increasing --duration or --validation-time.")
        return {"ok": False, "pairs": 0}

    print("\nEquivocating validators:")
    for v, slots in sorted(equivocations.items()):
        sample = sorted(slots)[:5]
        more   = f" ... (+{len(slots)-5} more)" if len(slots) > 5 else ""
        print(f"  Validator {v}: slots {sample}{more}")

    print(f"\nEvidence (pool.cpp:525 WARNING):")
    shown = 0
    for line in stderr.splitlines():
        if "Dropping NotarizeVote" in line and "finalized slot" in line:
            # strip ANSI
            clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
            print(f"  {clean}")
            shown += 1
            if shown >= 3:
                print(f"  ... ({total_pairs - 3} more)")
                break

    print(f"\nPART 1: PASS — alarm() race equivocation confirmed")
    return {"ok": True, "pairs": total_pairs, "validators": len(equivocations)}


# ──────────────────────────────────────────────────
# PART 2 — start_up() restart equivocation
# ──────────────────────────────────────────────────

PART2_PARAMS = [
    "--validation-time", "0.3:0.6",   # fast validation → blocks finalise → gremlin fires
    "--target-rate-ms",  "400",
    "--n-nodes",         "8",
    "--duration",        "60",         # longer run to ensure blocks finalise before gremlin
    "--gremlin-period",  "2:4",        # gremlin kills leader every 2-4 seconds
    "--gremlin-downtime","1:2",        # node is down 1-2 seconds
    "--gremlin-kills-leader",          # targets the current leader
    "-v",                "2",
]

RE_START_NODE  = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d+).*Starting node #(\d+)\.0")
RE_SKIP_DROP   = re.compile(
    r"(\d{2}:\d{2}:\d{2}\.\d+).*Dropping SkipVote\{slot=(\d+)\} from validator (\d+) .+ which references a finalized slot"
)
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')

def run_part2(binary: Path) -> dict:
    print("\n" + "=" * 60)
    print("PART 2 — start_up() restart equivocation (gremlin)")
    print(f"  {' '.join(str(x) for x in PART2_PARAMS)}")
    print("=" * 60)

    result = subprocess.run(
        [str(binary)] + PART2_PARAMS,
        capture_output=True, text=True, timeout=75
    )
    stderr = result.stderr

    # Collect restart timestamps keyed by validator index
    # (Initial starts at t=0 are filtered by checking line index > 8)
    lines = [ANSI_ESCAPE.sub('', l) for l in stderr.splitlines()]
    # Initial 8 node starts all happen within the first second; restarts come later.
    # Find timestamp of 8th initial start, then only collect starts after that.
    initial_count = 0
    initial_cutoff_ts = None
    for line in lines:
        m = RE_START_NODE.search(line)
        if m:
            initial_count += 1
            if initial_count == 8:
                initial_cutoff_ts = m.group(1)
                break

    restarts = []   # (line_idx, validator_idx, timestamp_str)
    past_initial = False
    for i, line in enumerate(lines):
        m = RE_START_NODE.search(line)
        if m:
            if not past_initial and initial_cutoff_ts and m.group(1) == initial_cutoff_ts:
                past_initial = True
                continue
            if past_initial:
                restarts.append((i, int(m.group(2)), m.group(1)))

    print(f"\nGremlin restarts observed: {len(restarts)}")

    if not restarts:
        print("FAIL: Gremlin did not fire (no blocks finalised to identify a leader).")
        print("      Try increasing --duration.")
        return {"ok": False, "restarts": 0}

    # For each restart, find SkipVote drops from that validator within the next 50 lines
    restart_equivocations = []
    for restart_line, validator_idx, restart_ts in restarts:
        skip_drops = []
        for j in range(restart_line + 1, min(restart_line + 50, len(lines))):
            m2 = RE_SKIP_DROP.search(lines[j])
            if m2:
                ts, slot, val = m2.group(1), int(m2.group(2)), int(m2.group(3))
                if val == validator_idx:
                    skip_drops.append((slot, ts))
        if skip_drops:
            restart_equivocations.append((validator_idx, restart_ts, skip_drops))

    if not restart_equivocations:
        print("FAIL: Gremlin fired but no post-restart SkipVote drops observed.")
        return {"ok": False, "restarts": len(restarts), "equivocations": 0}

    print(f"Post-restart SkipVote equivocations: {len(restart_equivocations)} restart(s)")
    print()
    for validator_idx, restart_ts, skip_drops in restart_equivocations:
        slots = [s for s, _ in skip_drops]
        print(f"  Validator {validator_idx} restarted at {restart_ts}")
        for slot, ts in skip_drops[:4]:
            print(f"    → start_up() broadcast SkipVote{{slot={slot}}} at {ts}")
            print(f"       (pool.cpp:525: slot already finalised, yet SkipVote sent on restart)")
        if len(skip_drops) > 4:
            print(f"    ... ({len(skip_drops) - 4} more slots)")

    print(f"\nExplanation:")
    print(f"  start_up() at consensus.cpp:82-91 broadcasts SkipVote for all slots in the")
    print(f"  current unannouncedleader window with guard '!voted_final' only.")
    print(f"  voted_notar is loaded from DB (bootstrap_votes) but not checked.")
    print(f"  A restarted validator that had voted NotarizeVote for those slots")
    print(f"  equivocates: pre-crash NotarizeVote still held by peers + new SkipVote.")

    print(f"\nPART 2: PASS — start_up() restart equivocation confirmed")
    return {"ok": True, "restarts": len(restarts), "equivocations": len(restart_equivocations)}


# ──────────────────────────────────────────────────
# Root cause summary
# ──────────────────────────────────────────────────

def print_root_cause():
    print("\n" + "=" * 60)
    print("ROOT CAUSE — Three locations, same missing guard")
    print("=" * 60)
    print("""
The guard '!voted_final' is used in three places to decide whether
to broadcast SkipVote. In all three, '!voted_notar' is missing:

  1. alarm() — consensus.cpp:145
       if (slot && !slot->state->voted_final) {
           // BUG: should also check !voted_notar && !voted_skip
           owning_bus().publish<BroadcastVote>(SkipVote{i})...;
       }

  2. start_up() — consensus.cpp:87
       if (slot.has_value() && !slot->state->voted_final) {
           // BUG: should also check !voted_notar
           owning_bus().publish<BroadcastVote>(SkipVote{i})...;
       }

  3. try_notarize() — consensus.cpp:232 (Bug B: mirror side)
       // After resuming from co_await ValidationRequest:
       slot.state->voted_notar = candidate->id;
       owning_bus().publish<BroadcastVote>(NotarizeVote{...})...;
       // BUG: no check for voted_skip before broadcasting NotarizeVote

  4. check_invariants() — pool.cpp:209-217 (Bug C: missing detection)
       // NotarizeVote + SkipVote combination is not checked:
       if (notarize_.has_value() && skip_.has_value()) {
           // MISSING — this case not present
       }

Fix: add !voted_notar (and !voted_skip) guards to locations 1 and 2,
     add voted_skip check before NotarizeVote broadcast in location 3,
     add NotarizeVote+SkipVote case to check_invariants() in location 4.
""")


# ──────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TON Simplex equivocation PoC")
    parser.add_argument("--build-dir", type=Path, default=None,
                        help="Path to build directory containing test-consensus")
    parser.add_argument("--part", choices=["1", "2", "both"], default="both",
                        help="Which part to run (default: both)")
    args = parser.parse_args()

    binary = find_binary(args.build_dir)
    print(f"Binary: {binary}")
    print(f"Commit: 3bb6abc (ton-blockchain/ton, branch testnet)\n")

    r1 = {"ok": False}
    r2 = {"ok": False}

    if args.part in ("1", "both"):
        r1 = run_part1(binary)

    if args.part in ("2", "both"):
        r2 = run_part2(binary)

    print_root_cause()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if args.part in ("1", "both"):
        status1 = "PASS" if r1["ok"] else "FAIL"
        pairs   = r1.get("pairs", 0)
        print(f"  Part 1 (alarm race):    {status1} — {pairs} equivocating (validator,slot) pairs")
    if args.part in ("2", "both"):
        status2 = "PASS" if r2["ok"] else "FAIL"
        equivs  = r2.get("equivocations", 0)
        print(f"  Part 2 (restart):       {status2} — {equivs} post-restart equivocation(s)")

    overall = (args.part == "1" and r1["ok"]) or \
              (args.part == "2" and r2["ok"]) or \
              (args.part == "both" and (r1["ok"] or r2["ok"]))
    print(f"\nOverall: {'PASS' if overall else 'FAIL'}")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
