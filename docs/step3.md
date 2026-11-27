# Step 3: self-operation and the first measured self-improvement

Issue #14 is a planned epic (specification section 10 step 3), not a ready
implementation issue. Its first acceptance criterion is to break the epic
into concrete issues before implementation; this page records that
breakdown, so the plan is versioned in the repository rather than only in
GitHub.

## What step 3 is

Section 9 (bootstrap and self-development) lets dev-org register its own
repo as an ordinary project and, within a versioned base frame, propose and
implement durable changes to its own software or workflow. The limits are
explicit (section 9.1): the owner sets a base frame once, an agent cannot
extend it or remove invariants, a separate deterministic control service
validates every change before activation, and only changes outside the
frame need an owner decision. Self-improvement never blocks ordinary
higher-priority work (section 9.2).

The bootstrap path is stepwise: manually built core, dogfooding in PR mode,
isolated candidate, controlled activation, gradual autonomy.

## The breakdown

The epic was split into five concrete issues, each with its own acceptance
criteria and delivery PR, delivered in dependency order:

| # | Issue | Delivers | A-tests |
|---|---|---|---|
| 35 | Improvement budget and candidate queue | separate low-priority interruptible improvement queue; self-work yields to user work | A03, A16, A48 |
| 36 | Isolated candidate environment | candidate runs on a separate test board/database/identity; cannot touch the active queue | A43 |
| 37 | Recoverable upgrade and blue/green activation | launcher activates a qualified version; active version keeps ownership until take-over; rollback | A14, A45, A49 |
| 38 | Measured self-improvement: replay baseline vs candidate | replay a recorded event sequence; compare candidate against baseline on the same task set and evaluator | A29, A47 |
| 39 | Change frame and promotion service | versioned base frame, policy controller, separate promotion service; bounded autonomous policy changes | A59, A60 |

The delivery order is `#35 -> #36 -> #37 -> #38 -> #39`: the queue and
budget first (so improvement work is interruptible and bounded), then the
isolated candidate (so a candidate cannot affect active work), then
activation and rollback (so an upgrade is recoverable), then measurement
(so the first improvement is compared against a baseline), and finally the
change frame (so bounded autonomous changes have a control boundary).

## The first measured improvement

Section 9 says the first own improvement issue after a successful pilot
should reduce the number of reconciliation calls without weakening the
wake-up deadline or the protection against double continuations. That
concrete improvement is delivered by issue #38, with measurements and event
traces linked to the issue and the existing acceptance tests still passing.
