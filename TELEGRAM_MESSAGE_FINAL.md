# TON Contest — Submission Messages
# One message per finding. Primary scope (1–4) first, secondary scope (5) second.
# Attach the corresponding HTML file as PDF to each message.

---

## Message 1 of 5 — Finding 1 (HIGH, Primary)
### Attach: submissions/finding-1-alarm-equivocation.html (as PDF)

---

**[HIGH] Honest Validator Self-Equivocation: SkipVote + NotarizeVote for the Same Slot**

**Repository:** ton-blockchain/ton · branch testnet · commit 3bb6abc  
**Scope:** validator/consensus/simplex/ (primary)

**Summary:**
Three linked bugs in `consensus.cpp` and `pool.cpp` allow an honest validator to broadcast both a SkipVote and a NotarizeVote for the same slot during normal operation. Equivocation is silently ignored by peers — no MisbehaviorReport is generated. Under conditions where block validation exceeds the alarm interval, every validator equivocates simultaneously, causing complete liveness failure for the affected rounds.

**Bug A** (`alarm()`): Guard checks only `!voted_final`, missing `!voted_notar && !voted_skip`. Fires SkipVote during a pending notarization.

**Bug B** (`try_notarize()`): Does not check `voted_skip` after resuming from `co_await ValidationRequest`. Fires NotarizeVote after alarm has already set `voted_skip = true`.

**Bug C** (`check_invariants()`): `NotarizeVote + SkipVote` combination is absent from the invariant check. The equivocation is accepted without any misbehavior report.

**Reproduced:** 523 confirmed equivocating (validator, slot) pairs in a single 30-second run across all 8 validators. Command and evidence in attached report.

Build requires Clang 18+ (GCC cannot compile this codebase).

---

## Message 2 of 5 — Finding 2 (HIGH, Primary)
### Attach: submissions/finding-2-startup-equivocation.html (as PDF)

---

**[HIGH] start_up() Bootstrap Replay Equivocates on Every Validator Restart**

**Repository:** ton-blockchain/ton · branch testnet · commit 3bb6abc  
**Scope:** validator/consensus/simplex/consensus.cpp (primary)

**Summary:**
The same missing guard as the alarm() race (Finding 1) also exists in the startup bootstrap replay path — but fires deterministically on every restart, not under a race condition. Any validator that restarts after having cast a NotarizeVote in an unfinished leader window immediately broadcasts SkipVote for that slot on startup.

**Root cause:** `start_up()` loads `voted_notar` from persistent DB (lines 47–80), then broadcasts SkipVote for all non-final slots in the current unannouncedwindow (lines 82–91) with the guard `!voted_final` only — missing `!voted_notar`.

**Trigger:** Validator crashes or is restarted after sending NotarizeVote{slot X} in window W, before window W advances. Pre-crash NotarizeVote{X} remains in peers' pools. Restart broadcasts SkipVote{X}. Equivocation.

This is the third location of the same missing-guard bug. Unlike the runtime race, no timing coincidence is required — it fires unconditionally on every restart matching this state.

Full analysis and fix in attached report.

---

## Message 3 of 5 — Finding 3 (MEDIUM, Primary)
### Attach: submissions/finding-3-conflicting-candidate-no-evidence.html (as PDF)

---

**[MEDIUM] ConflictingCandidateAndCertificate Misbehavior Stores No Cryptographic Evidence**

**Repository:** ton-blockchain/ton · branch testnet · commit 3bb6abc  
**Scope:** validator/consensus/simplex/pool.cpp + misbehavior.h (primary)

**Summary:**
Every call site that creates a `ConflictingCandidateAndCertificate` misbehavior report passes no arguments — the candidate and conflicting certificate are commented out at all four call sites (pool.cpp lines 646, 656, 666, 676). The factory `create()` stores nothing and produces an empty report.

A Byzantine leader can propose candidates that conflict with existing certificates and face zero on-chain consequence: the detection is local only and the misbehavior cannot be proven to other nodes or to the elector contract.

The four call sites cover: candidate with invalid parent chain, candidate conflicting with notarized block, candidate with wrong parent at finalization boundary, and candidate whose parent is notarized as a different block.

Fix: add candidate and certificate parameters to `create()`, store them, implement serialization.

Full analysis in attached report.

---

## Message 4 of 5 — Finding 4 (MEDIUM, Primary)
### Attach: submissions/finding-4-fixme-misbehaviors.html (as PDF)

---

**[MEDIUM] Three Misbehavior Detection Code Paths Silently Drop Byzantine Behaviour**

**Repository:** ton-blockchain/ton · branch testnet · commit 3bb6abc  
**Scope:** validator/consensus/simplex/consensus.cpp (primary)

**Summary:**
Three detectable Byzantine conditions in `consensus.cpp` are silently dropped with `// FIXME: Report misbehavior` comments:

1. **consensus.cpp:174** — Candidate with `parent_slot ≥ own_slot` (invalid block structure). Rejected locally, no report filed.

2. **consensus.cpp:180** — Leader sends two different candidates for the same slot (proposal equivocation). Second candidate silently ignored, no report filed.

3. **consensus.cpp:227** — Block candidate fails full validation (`CandidateReject`). Logged as WARNING, no misbehavior report filed.

All three cases allow a Byzantine leader to degrade liveness — forcing re-validation, occupying ValidationRequest slots, wasting bandwidth — with no slashing risk. The evidence needed for a report is available in scope at each location.

Full analysis and proposed fix in attached report.

---

## Message 5 of 5 — Finding 5 (MEDIUM, Secondary)
### Attach: submissions/finding-5-twostep-amplification.html (as PDF)

---

**[MEDIUM] TwoStep Broadcast: Deduplication Check Placed After Rebroadcast**

**Repository:** ton-blockchain/ton · branch testnet · commit 3bb6abc  
**Scope:** overlay/broadcast-twostep.cpp (secondary)

**Summary:**
In both the simple (line 314) and FEC (line 347) paths of `process_broadcast()`, `rebroadcast()` is called before `is_delivered()`. Any node can replay a previously seen broadcast within the ±20-second timestamp window and cause every relay node to forward the duplicate to all N−1 peers before recognising it as a duplicate.

For an N=300 overlay, each replay generates 89,402 messages across the network. No per-sender deduplication or rate limiting exists on the relay path. `check_broadcast()` in `private-overlay.cpp` unconditionally accepts all overlay broadcasts.

**Fix:** move `is_delivered()` check before `rebroadcast()` in both paths.

Full analysis with amplification table in attached report.
