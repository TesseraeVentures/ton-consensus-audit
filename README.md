# TON Simplex Consensus — Security Audit

**Contest:** TON Blockchain Contest Round 2  
**Scope:** `validator/consensus/simplex/` (primary) · `overlay/` (secondary)  
**Repo:** ton-blockchain/ton · branch `testnet` · commit `3bb6abc`  
**Date:** 2026-03-14  

---

## Findings Summary

| # | Severity | Scope | Title |
|---|----------|-------|-------|
| 1 | **HIGH** | Primary | alarm() race: honest validator self-equivocation (523 confirmed events) |
| 2 | **HIGH** | Primary | start_up() restart equivocation (fires deterministically on every restart) |
| 3 | MEDIUM | Primary | ConflictingCandidateAndCertificate stores no cryptographic evidence |
| 4 | MEDIUM | Primary | Three misbehavior detection FIXMEs never implemented |
| 5 | MEDIUM | Secondary | TwoStep broadcast: rebroadcast() before is_delivered() in both paths |

---

## Quick Start — Docker (Recommended)

**No build required.** Run the PoC in one command:

```bash
docker run --rm ghcr.io/tesseraeventures/ton-consensus-audit:latest
```

This runs the combined PoC for Findings 1 & 2. Expected output (30 seconds):

```
PART 1 — alarm() race equivocation
  --validation-time 1.5:2.5 --target-rate-ms 200 --n-nodes 8 --duration 30 -v 2

Result: 10+ equivocating (validator, slot) pairs
        8 / 8 validators affected

Evidence (pool.cpp:525 WARNING):
  Dropping NotarizeVote{id={58, ...}} from validator 5 ... which references a finalized slot
  ...

PART 1: PASS — alarm() race equivocation confirmed
```

Each `pool.cpp:525` warning line proves a validator broadcast both `SkipVote` AND `NotarizeVote` for the same slot.

### Alternative PoC runs

```bash
# Finding 1 only (alarm race)
docker run --rm ghcr.io/tesseraeventures/ton-consensus-audit:latest \
  python3 /audit/poc/test_equivocation.py

# Finding 5 (TwoStep amplification — source inspection)
docker run --rm ghcr.io/tesseraeventures/ton-consensus-audit:latest \
  python3 /audit/poc/test_twostep_amplification.py --check-source-only
```

---

## Files

### Submission PDFs (one per finding — contest requires separate messages)
- `submissions/finding-1-alarm-equivocation.pdf`
- `submissions/finding-2-startup-equivocation.pdf`
- `submissions/finding-3-conflicting-candidate-no-evidence.pdf`
- `submissions/finding-4-fixme-misbehaviors.pdf`
- `submissions/finding-5-twostep-amplification.pdf`

### Full Report
- `ton-consensus-audit-full-report.pdf` — comprehensive document, all 5 findings

### Telegram Submission Templates
- `TELEGRAM_MESSAGE_FINAL.md` — 5 copy-paste messages, one per finding

### PoC Scripts
- `poc/test_equivocation_combined.py` — confirms Findings 1 & 2 (alarm race + restart equivocation)
- `poc/test_equivocation.py` — confirms Finding 1 only (alarm race, 523 events)
- `poc/test_twostep_amplification.py` — confirms Finding 5 (TwoStep line ordering)

---

## Verifying Findings 2–5 (source inspection)

All code-only findings — check the exact lines in the `testnet` branch at commit `3bb6abc`:

| Finding | File | Lines | What to check |
|---------|------|-------|---------------|
| 2 | `validator/consensus/simplex/consensus.cpp` | 82–91 | Guard is `!voted_final` only — missing `!voted_notar` |
| 3 | `validator/consensus/simplex/pool.cpp` | 646, 656, 666, 676 | Evidence args commented out in all 4 calls |
| 3 | `validator/consensus/simplex/misbehavior.h` | `create()` | Factory takes no args, stores nothing |
| 4 | `validator/consensus/simplex/consensus.cpp` | 174, 180, 227 | Three `// FIXME: Report misbehavior` comments |
| 5 | `overlay/broadcast-twostep.cpp` | 313–316, 346–352 | rebroadcast() before is_delivered() in both paths |

---

## Building from Source (Alternative)

If you prefer to build locally instead of using Docker:

### Prerequisites

| Platform | Install |
|----------|---------|
| **macOS** | `brew install llvm openssl cmake` |
| **Ubuntu/Debian** | `apt install clang-18 libssl-dev cmake build-essential autoconf automake libtool` |
| **Fedora** | `dnf install clang openssl-devel cmake` |

### Step 1: Clone TON (with submodules)

```bash
git clone --branch testnet --recursive https://github.com/ton-blockchain/ton.git
```

> **⚠️ `--recursive` is required.** TON has 14 submodules.
> If you already cloned without it, run:
> ```bash
> cd ton && git submodule update --init --recursive
> ```

### Step 2: Configure with CMake

**macOS (Apple Silicon / Intel):**
```bash
export CC=$(brew --prefix llvm)/bin/clang
export CXX=$(brew --prefix llvm)/bin/clang++

cd ton && mkdir build-clang && cd build-clang
cmake .. -DCMAKE_BUILD_TYPE=Release \
  -DOPENSSL_ROOT_DIR=$(brew --prefix openssl) \
  -DOPENSSL_INCLUDE_DIR=$(brew --prefix openssl)/include \
  -DOPENSSL_CRYPTO_LIBRARY=$(brew --prefix openssl)/lib/libcrypto.dylib \
  -DOPENSSL_SSL_LIBRARY=$(brew --prefix openssl)/lib/libssl.dylib
```

**Linux:**
```bash
export CC=clang-18
export CXX=clang++-18

cd ton && mkdir build-clang && cd build-clang
cmake .. -DCMAKE_BUILD_TYPE=Release
```

### Step 3: Build only `test-consensus`

```bash
# macOS
cmake --build . --target test-consensus -j$(sysctl -n hw.logicalcpu)

# Linux
cmake --build . --target test-consensus -j$(nproc)
```

The binary will be at `build-clang/test/consensus/test-consensus`.

### Step 4: Run the PoC

```bash
# From the audit repo root:
python3 poc/test_equivocation_combined.py --build-dir /path/to/ton/build-clang
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `OpenSSL config failed` | Pass `-DOPENSSL_ROOT_DIR=$(brew --prefix openssl)` (macOS) |
| `does not contain a CMakeLists.txt file` (abseil-cpp, crc32c, etc.) | Submodules missing — run `git submodule update --init --recursive` |
| `No download info given for 'libbacktrace_external'` | Same — submodules not initialised |
| `command not found: systctl` | Typo — it's `sysctl` (no extra `t`) |
| GCC compilation errors | Use Clang 18+ — TON's coroutine code requires it |
| Submodule clone times out | Use `--depth 1` for shallow clones, or use Docker |
