# Reviewed scenario planning roadmap

## Responsibility check

The configured `RiskProvider` is responsible for proposing scenarios. It receives only
eligible, accepted `OBSERVED` and `FORECAST` signal-version references and may select
those immutable references plus propose new `HYPOTHETICAL` disruptions. Deterministic
platform code validates every selection and the connected client normalizes and
reconciles every disruption.

Before this iteration, `POST /api/planning/cycles` discarded every generated scenario
except the first and immediately submitted that scenario for simulation. That prevented
review before execution.

## Iterations

1. **Generate without executing.** Persist all client-reconciled risk scenarios in a
   `PROPOSED` planning cycle. No simulation endpoint is invoked during generation.
2. **Review the combined scenario.** Present every unique generated disruption and let
   the user include or exclude it. Deterministic code rejects unknown IDs, an empty
   selection, incompatible disruptions, and invalid signal relationships before
   freezing the reviewed composition.
3. **Run explicitly.** Add a separate baseline-submit operation. Only this user action
   invokes the connected client's simulation endpoint. Queued runs remain refreshable.
4. **Plan from results.** After authoritative baseline metrics are available, invoke the
   configured planner with those exact results and show both the result and proposals.
5. **Evaluate and decide.** Keep intervention simulations and deterministic ranking
   explicit. A human may reject a proposal, while approval remains restricted to the
   ranked recommendation. Neither decision executes an operational intervention.

Each iteration is covered by service/API lifecycle tests, pure UI-rule tests, and the
workflow documentation in `simulation-and-planning.md` and `api-reference.md`.

## Merged simulation-to-planning iteration

The reviewed scenario remains the last human input before baseline execution. After the
user selects **Simulate**, AEGIS owns the transition from the client simulation result to
planner proposals. The browser no longer asks the user to transcribe entity IDs or invoke
a separate plan-generation action.

1. **Unify baseline advancement.** Baseline submission and refresh use one orchestration
   path. A queued run remains refreshable; a completed run is retrieved once and its
   authoritative result is persisted before planning begins.
2. **Plan immediately from authoritative results.** The same orchestration derives the
   allowed entity IDs from the frozen scenario, loads the client intervention catalog,
   sends the unchanged baseline result to the configured planner, validates every
   returned intervention through the client, and persists the resulting plans. Existing
   plans prevent duplicate planner invocation on later refreshes.
3. **Collapse the human-facing transition.** Before execution the user reviews the risk
   composition. After execution starts, the primary view shows processing state followed
   by the authoritative simulation result and generated plans. There is no raw entity-ID,
   objective, constraint, proposal-limit, or separate plan-generation form at this stage;
   objectives and constraints are frozen when the cycle is created.
4. **Retain explicit evaluation and decision controls.** Generated plans remain visible
   for intervention simulation, deterministic comparison/ranking, and the final human
   approval or rejection. Approval records a decision and does not execute operational
   changes in the connected client.
5. **Verify failure boundaries.** Tests cover immediate and queued completion,
   exactly-once planner invocation, scenario-derived entity scope, unchanged authoritative
   metrics, unavailable intervention capabilities, invalid planner output, and UI removal
   of the intermediate generation form.

Acceptance requires a single user simulation action to yield baseline results and plans
when the client completes synchronously, or the same combined payload after automatic
polling when it completes asynchronously.
