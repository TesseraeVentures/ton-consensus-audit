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

### Source HTML
- `report.html` — master report source
- `submissions/*.html` — individual finding sources

### PoC Scripts
- `poc/test_equivocation.py` — confirms Finding 1 (alarm race, 523 events)
- `poc/test_twostep_amplification.py` — confirms Finding 5 (TwoStep line ordering)

---

## Reproducing Finding 1 (requires Clang 18+)

```bash
# macOS
brew install llvm
export CC=$(brew --prefix llvm)/bin/clang
export CXX=$(brew --prefix llvm)/bin/clang++

git clone --branch testnet https://github.com/ton-blockchain/ton.git
cd ton && mkdir build-clang && cd build-clang
cmake .. -DCMAKE_BUILD_TYPE=Release -DTON_USE_ROCKSDB=OFF
cmake --build . --target test-consensus -j$(sysctl -n hw.logicalcpu)

./test/consensus/test-consensus \
  --validation-time 1.5:2.5 --target-rate-ms 200 --n-nodes 8 --duration 30 -v 2 2>&1 \
  | grep "Dropping NotarizeVote.*finalized slot"
```

Expected: multiple `WARNING [pool.cpp:525]` lines — each one proves a validator broadcast both `SkipVote` and `NotarizeVote` for the same slot.

## Verifying Findings 2–5 (source inspection only)

All code-only findings — just check the exact lines in the testnet branch at commit `3bb6abc`:

| Finding | File | Lines | What to check |
|---------|------|-------|---------------|
| 2 | `validator/consensus/simplex/consensus.cpp` | 82–91 | Guard is `!voted_final` only — missing `!voted_notar` |
| 3 | `validator/consensus/simplex/pool.cpp` | 646, 656, 666, 676 | Evidence args commented out in all 4 calls |
| 3 | `validator/consensus/simplex/misbehavior.h` | `create()` | Factory takes no args, stores nothing |
| 4 | `validator/consensus/simplex/consensus.cpp` | 174, 180, 227 | Three `// FIXME: Report misbehavior` comments |
| 5 | `overlay/broadcast-twostep.cpp` | 313–316, 346–352 | rebroadcast() before is_delivered() in both paths |
