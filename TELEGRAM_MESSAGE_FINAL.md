# TON Contest — Submission Messages
# One message per finding. Attach the corresponding PDF + the PoC archive to each message.
# Submit to @ton_bug_bounty_contest
# Attach: ton-consensus-audit-poc.tar.gz (PoC scripts + Dockerfile + README)

---

## Message 1 of 5 — Finding 1 (HIGH, Primary)
### Attach: submissions/finding-1-alarm-equivocation.pdf + ton-consensus-audit-poc.tar.gz

---

**Title:** Honest Validator Self-Equivocation via alarm() Race

**Impact:** All honest validators simultaneously equivocate (broadcast SkipVote + NotarizeVote for the same slot) during normal operation whenever block validation exceeds the alarm interval. Equivocation is silently accepted — no MisbehaviorReport generated. Under sustained load, this causes complete liveness failure for affected rounds.

**Description:**
Three linked bugs in `consensus.cpp` and `pool.cpp` (testnet branch, commit 3bb6abc):
- **Bug A** (`consensus.cpp:144-150`): `alarm()` guard checks only `!voted_final`, missing `!voted_notar && !voted_skip`. Fires SkipVote during pending notarization.
- **Bug B** (`consensus.cpp:232-235`): `try_notarize()` does not check `voted_skip` after `co_await ValidationRequest`. Fires NotarizeVote after alarm already set `voted_skip = true`.
- **Bug C** (`pool.cpp:209-217`): `check_invariants()` missing `NotarizeVote + SkipVote` case — equivocation accepted silently.

**Reproduction:**
```
docker run --rm ghcr.io/tesseraeventures/ton-consensus-audit:latest
```
Runs in 30 seconds. Expected: 10-25+ equivocating (validator, slot) pairs across all 8 validators, evidenced by `pool.cpp:525` WARNING lines.

Or manually: build `test-consensus` from testnet branch with Clang 18+, then:
```
./test-consensus --validation-time 1.5:2.5 --target-rate-ms 200 --n-nodes 8 --duration 30 -v 2
```
Grep for `"Dropping NotarizeVote.*finalized slot"`.

Source + Dockerfile: https://github.com/TesseraeVentures/ton-consensus-audit

Full analysis in attached PDF.

---

## Message 2 of 5 — Finding 2 (HIGH, Primary)
### Attach: submissions/finding-2-startup-equivocation.pdf

---

**Title:** start_up() Bootstrap Replay Equivocates on Every Validator Restart

**Impact:** Any validator that restarts after casting a NotarizeVote in an unfinished leader window immediately equivocates by broadcasting SkipVote for that same slot. Fires deterministically on every restart matching this state — no race condition required.

**Description:**
Same missing guard as Finding 1, different code path (`consensus.cpp:82-91`). `start_up()` loads `voted_notar` from persistent DB, then broadcasts SkipVote for all non-final slots using only `!voted_final` guard — missing `!voted_notar`. Pre-crash NotarizeVote remains in peers' pools → restart broadcasts SkipVote → equivocation.

**Reproduction:**
Same Docker image as Finding 1:
```
docker run --rm ghcr.io/tesseraeventures/ton-consensus-audit:latest
```
PART 2 of the output demonstrates startup equivocation.

Alternatively, inspect `consensus.cpp` lines 82-91: the loop broadcasts SkipVote with guard `!voted_final` only.

Full analysis in attached PDF.

---

## Message 3 of 5 — Finding 3 (MEDIUM, Primary)
### Attach: submissions/finding-3-conflicting-candidate-no-evidence.pdf

---

**Title:** ConflictingCandidateAndCertificate Misbehavior Stores No Cryptographic Evidence

**Impact:** A Byzantine leader can propose candidates conflicting with existing certificates with zero on-chain consequence. Detection is local-only; the misbehavior cannot be proven to other nodes or the elector contract.

**Description:**
All four call sites creating `ConflictingCandidateAndCertificate` in `pool.cpp` (lines 646, 656, 666, 676) pass no arguments — the candidate and certificate parameters are commented out. The `create()` factory stores nothing.

**Reproduction:**
Inspect `pool.cpp` lines 646, 656, 666, 676 and `misbehavior.h` create() at commit 3bb6abc. All four call sites have empty constructors.

Full analysis in attached PDF.

---

## Message 4 of 5 — Finding 4 (MEDIUM, Primary)
### Attach: submissions/finding-4-fixme-misbehaviors.pdf

---

**Title:** Three Misbehavior Detection Code Paths Silently Drop Byzantine Behaviour

**Impact:** A Byzantine leader can degrade liveness — forcing re-validation, wasting bandwidth — with no slashing risk. Three detectable misbehaviors are silently ignored.

**Description:**
Three `// FIXME: Report misbehavior` comments in `consensus.cpp`:
1. **Line 174:** Candidate with `parent_slot >= own_slot` — rejected locally, no report.
2. **Line 180:** Leader sends two different candidates for same slot — silently ignored, no report.
3. **Line 227:** Block candidate fails validation (CandidateReject) — logged as WARNING, no report.

**Reproduction:**
Inspect `consensus.cpp` lines 174, 180, 227 at commit 3bb6abc. All three have `// FIXME` comments with no report implementation.

Full analysis in attached PDF.

---

## Message 5 of 5 — Finding 5 (MEDIUM, Secondary)
### Attach: submissions/finding-5-twostep-amplification.pdf

---

**Title:** TwoStep Broadcast: Deduplication Check Placed After Rebroadcast

**Impact:** Any node can replay a previously seen broadcast within the ±20s timestamp window, causing every relay to forward the duplicate to all N-1 peers before recognizing it. For N=300 overlay, each replay generates ~89,000 messages.

**Description:**
In `overlay/broadcast-twostep.cpp`, both simple (line 314) and FEC (line 347) paths of `process_broadcast()` call `rebroadcast()` before `is_delivered()`. No per-sender deduplication or rate limiting exists on the relay path.

**Reproduction:**
Inspect `broadcast-twostep.cpp` lines 313-316 (simple path) and 346-352 (FEC path) at commit 3bb6abc. `rebroadcast()` precedes `is_delivered()` in both.

Or run:
```
docker run --rm ghcr.io/tesseraeventures/ton-consensus-audit:latest \
  python3 /audit/poc/test_twostep_amplification.py --check-source-only
```

Full analysis in attached PDF.
