# Highlights — what broke, and what each break established

Groundwork was built over **54 days** (2026-07-05 → 2026-08-27), **144 commits**
on `main`, **42 merged pull requests**, **76 session journal entries**, and five
phase gates (`p0-gate` … `p4-gate`).

This file is the chronology the public repository's authored history cannot
show. It is curated from a private build journal, and it contains **no corpus
content** — every incident is described by its mechanism, never by the
documents involved.

The through-line: **almost every rule in this system was purchased by a
failure.** What follows is the receipt.

---

## The case law

Each of these is a sentence the build earned. They appear in the order they
were minted, with the incident that bought them.

### "Floors, not averages"
*P1-T7.* A re-ranker was added to improve retrieval precision. Average scores
improved; a pure cross-encoder ranking **broke the recall floor** — some
questions lost their source document entirely, invisible in the mean. The fix
was a blend; the lesson is that an aggregate that improves while a floor
collapses is a metric hiding a regression.

### "Thresholds belong to their input distribution"
*P1-T8, re-proven at P5-T3.* The not-found gate's threshold was derived from
one corpus's re-rank score distribution. Reusing it elsewhere is reusing a
*measurement* as if it were a *constant*. The demo corpus later produced a
margin of 0.1014 against the original's 0.8008 — the same pipeline, an eight
times narrower safety band — which made the rule concrete rather than
theoretical. Every evaluation run now prints its margin so decay announces
itself.

### "The exam is right; the product should honor it"
*P1-T4 onward.* Exam cases are amended only on verbatim source evidence, never
because the product finds them inconvenient. When a correct, correctly-cited
answer failed a case, the *string* was the defect — that is the one amendment
shape the rule allows.

### "A test the defense never faced is not a passed test"
*P3-T1.* A trajectory evaluator was written to catch citation laundering. It
was only trustworthy once a **deliberately laundered fixture** was planted and
shown to fail the check. That fixture now rides in CI permanently.

### "Enforced stays fresh, manual rots"
*2026-08-03, the most embarrassing entry in the journal.* The project's own
state file went **stale for twelve consecutive closeouts** without anyone
noticing. The cause: an update written with a string-replace that printed
`ok` unconditionally, so the first anchor mismatch silently no-op'd and every
later update referenced the previous one's output. It survived because the
state file is the one document nobody reads *during* a session — its whole job
is cold-resume, so its staleness is invisible until a resume needs it.

### "Constructed-safe over hoped-recovered"
*P5, the decision that shaped this repository.* Publishing meant either
scrubbing 120 commits of history — a property one *hopes* was recovered, whose
success condition nobody can verify and whose failure is permanent and public —
or constructing a clean repository file by file. The scanner later demonstrated
the argument rather than asserting it: an orphan-branch "fresh start" of a
leaked repository **still scanned red**, because the old ref survives. Only a
genuinely new repository came up clean.

### "A gate must never report a verdict it did not earn"
*P5-T1.* Three sibling failures in one instrument: a check that would pass
vacuously on an empty seed set; a check whose scope could be silently narrowed
out from under its verdict; and a control reachable only if a human remembered
a flag. All three produce a PASS that describes something other than what the
gate claims to measure. The remedy in each case was to make the unearned
verdict *unreachable*, not to document a caution.

### "A control that depends on remembering a flag is not a control"
*P5-T1 gate.* A seed class was ratified as included in the one-time pre-publish
sweep. Verification found the sweep did not include it — the class was reachable
only behind an opt-in flag a human had to remember at the exact moment it
mattered. Coverage at the one moment it matters must be structural.

### "An escalation nobody reads is not an escalation"
*P5-T2.* A watchdog detected a real failure, could not fix it, and escalated
"human required" — twice, unattended, into a log file and a desktop
notification nobody saw. The failure it announced was still there three weeks
later and blocked a task. A control can be perfectly correct and still be
inert, because its output has no destination.

### "A flag is a claim; an untested flag is an unverified claim"
*P5-T4, twice in one day.* One flag accepted a file path and silently ignored
it whenever another code path happened to succeed. Another flag named
`--structural-only` softened a refusal without ever restricting what it
scanned, so it ran a full scan and called itself reduced. Both parsed. Both had
docstrings. Neither had a test. Every flag now gets a test proving it *changes
behavior*.

### "You cannot be careful enough out of a self-referential trap"
*P5-T2 → T4, four instances, each produced by fixing the previous one.* A leak
detector hardcoded the private names it hunted — publishing its own seed list.
The comment explaining that fix listed real private document titles as
examples. The *test* written to forbid hardcoded names contained the names, in
a file that ships. The fourth was caught by the machine rather than a human: a
provenance file written by the build tooling named the private repository, and
the sweep flagged it.

The pattern: **any check about strings, written in strings that ship, is a
disclosure surface — and the more carefully it is documented, the larger that
surface grows.** Care makes it worse, because care means more explanation and
every explanation is more shipped text. The escape is structural: move the
content out of the artifact, and let what remains assert *structure* instead of
*content*.

### "A check that has never run is a claim, not a check"
*P5-T4.* This repository's required status check had never executed. The
workflow triggered on pull requests only, and the repository was bootstrapped
by a direct push, so the trigger never fired. The check existed, was
configured, was named as required, and had produced exactly zero evidence.

Its sibling arrived hours later: a branch-protection rule was enabled and
*active*, a direct push was correctly rejected — and a pull request with a
**failing** check merged anyway, because the rule set contained no
required-status-check rule at all. Commit `c8427b9` in this history is the
empty commit that proved the first half, and it is left in place deliberately
as the receipt. **An enabled control is not a specified control.**

A third sibling, and the sharpest of the three: once the rule *was* added, its
context was **mistyped** — `offline tests` with a space, against a check
reporting itself as `offline-tests` with a hyphen. The rule was configured,
active, and marked **Required**, and it would have waited forever for a string
nothing would ever report. It **failed closed**, which is why it was safe
rather than dangerous, and it was **invisible until a real pull request met
it** and sat at *"Expected — Waiting for status to be reported"* with its merge
button disabled. **Verify a required check's context against the reporting
context byte-for-byte; never type it from memory.**

### "A correct remedy behind an incorrect verdict is a more destructive bug"
*P5-T4, the sharpest lesson of the build.* A watchdog existed to recover a
stale container backend. It was hardened — correctly — to escalate from a
polite signal to a forceful one, because the observed failure mode was a
process that ignores polite signals.

Then it was installed as a scheduled agent, where the runtime environment
supplies a minimal `PATH`. The binary it probes was not on that path, so the
probe returned *command not found*, and the code read **any** non-zero result
as "the subject is broken". For hours it killed and relaunched a **perfectly
healthy** service every fifteen minutes — and the recent hardening made each
cycle destructive rather than merely noisy.

The hardening was a genuine improvement. Sitting behind a false verdict, it
turned a spurious alarm into a machine-killer. **Improving the remedy while
leaving the decision unexamined is how a monitor becomes the outage.**

### "A monitor that cannot probe must not conclude failure"
*The fix for the above, and the second instrument under one rule.* The leak
scanner's three-valued contract — clean / found / **cannot verify** — became
the watchdog's: healthy / stale / **cannot probe → log loudly, act on
nothing**. A path patch alone would have fixed that instance and left the
reasoning error in place. **An instrument that collapses "no signal" into "bad
signal" will eventually act, destructively, on its own blindness.**

### "A resource with no monitor is an outage waiting for a threshold"
*Recurring.* Five dependencies were discovered to be unowned, each by an
outage and never by a check: background processes, containers, database state,
a local model store wiped by an unrelated update, and finally **disk**, which
filled mid-task and made every tool call fail. Each had a "someone would
notice" assumption behind it. Nobody noticed any of them.

### "A disposition row asserting a property must cite its verification"
*P5-T4, a correction to earlier work.* A sanitization inventory contained the
row *"code and test fixtures use synthetic ids already."* It was **asserted,
never verified** — and the pre-publish sweep falsified it by finding a real
private identifier in a test fixture. The inventory's value was never its
confidence; it was supposed to be its evidence.

### "Three views of the same instant are one observation, not three confirmations"

*The verification rule the last night produced.* A required-check rule was
reported missing — and the report cited **three independent angles**: the rule
set's own rule list, an enumeration of every rule set, and the platform's
computed effective-rules view. All three agreed. All three were also queried
within the same few seconds, *before the change being looked for had been
saved*.

**Independence has to be in the evidence, not in the endpoint.** Querying one
fact three ways proves only that three endpoints agree with each other; it says
nothing about whether the fact was true a minute later. The apparent weight of
"three angles" stood in for the passage of time, and a correct hypothesis —
that the context string was mistyped — looked refuted when it was right.

The rule that follows: **when a read contradicts a claim that something was
just changed, re-read after the change could have landed.** A read taken before
a save is not a refutation.

---

## The incidents, in order

| When | What happened | What it established |
|---|---|---|
| 2026-07-05 | Gateway silently self-loaded environment config and hijacked a shared variable name | App-owned variables carry an explicit prefix; the launch path is one script, not a remembered command |
| 2026-07-06 | An unquoted `&` in a config value broke shell sourcing mid-file | All config values quoted — a convention, enforced by the file that documents it |
| 2026-07-06 | Container backend went stale, holding locks for 27 hours | First of five occurrences; the drill was written down |
| 2026-07-07 | A provider key leaked from the dispatching shell into a subprocess and took precedence over subscription auth, killing the run at its spend cap | Provider keys are stripped from worker environments |
| 2026-07-08 | Layer-1 pass counts flapped run to run | Generation temperature pinned to 0 as **product** behaviour — an eval-only pin would create eval/production skew |
| 2026-07-09 | A cross-encoder improved averages and broke the recall floor | *Floors, not averages* |
| 2026-07-09 | Judge calibration appeared to drift | Root cause was apples-to-oranges by design; fixed with **frozen anchors**, so agreement measures the judge's movement alone |
| 2026-07-12 | The corpus grew mid-build, invalidating comparisons | Re-lock runs are mandatory after corpus growth |
| 2026-07-13 | A local model store was wiped by an unrelated update | Fourth unowned dependency named |
| 2026-07-14 | A direct push to the protected branch happened by hand | A pre-push hook now blocks it — discipline converted to a mechanism |
| 2026-07-15 | A third-party agent session **trifurcated the repository** | All repository-level operations became owner-gated; deletion is human-only, permanently |
| 2026-07-17 | A judge's score parser truncated on nested braces in rationales — latent for a phase | Found by a bonus check, not by the failure it was causing |
| 2026-07-17 | Checkpoints were being written as savepoints, so a killed run lost work it had already paid for | Found by a **kill drill**, not by review; the store now refuses non-autocommit connections |
| 2026-08-02 | An injection planted in retrieved content reached the generator | Refused as data **and logged with its source** — a block nobody can see afterwards is not a control |
| 2026-08-03 | The state file found stale for twelve closeouts | *Enforced stays fresh, manual rots* |
| 2026-08-09 | A leak scanner's first canary run | A leak that survives only in history is still a leak; an orphan-branch "clean start" cleans nothing |
| 2026-08-26 | Container backend stale, occurrence #5; the documented drill escalated "human required" and had already done so twice, unattended, three weeks earlier | *An escalation nobody reads is not an escalation* |
| 2026-08-26 | The drill's own remedy was too polite to work on an unresponsive process | Escalate to a forceful signal — a remedy whose premise is "unresponsive" cannot ask nicely |
| 2026-08-27 | The pre-publish sweep found a real private identifier in a test fixture, contradicting a written inventory row | *A disposition row must cite its verification* |
| 2026-08-27 | The watchdog killed a healthy service every 15 minutes for hours | *A correct remedy behind an incorrect verdict is a more destructive bug*; *a monitor that cannot probe must not conclude failure* |
| 2026-08-27 | A pull request with a failing check merged into a protected branch | *An enabled control is not a specified control* |
| 2026-08-27 | A required check, once added, was configured with a mistyped context and waited forever for a string nothing would report — caught only when a real PR sat at "Expected" with its merge disabled | Verify a required check's context against the reporting context byte-for-byte |
| 2026-08-27 | A rule was reported missing on the strength of three API reads — all taken seconds apart, before the change had been saved | *Three views of the same instant are one observation, not three confirmations* |

---

## What the numbers cost

| | |
|---|---|
| Whole project through the P2 gate | **$6.99** across 2,293 traces |
| A single grounded answer | ~$0.006 blended (personal), $0.0019 measured (demo) |
| A multi-step research brief | ~$0.095 — 11–14× a single answer |
| A declined question | **$0.00** — the not-found gate spends zero generation tokens |

The cheapest measurement in the system is the one that says *I don't know*.
