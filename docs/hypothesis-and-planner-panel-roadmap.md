# Hypothesis and stub planner-panel roadmap

## Scope

This iteration adds prompt-driven hypothetical risk proposals, browser-local review,
and a user-selectable deterministic planner panel. Notifications and configurable
multi-agent definitions, per-role panel prompts, skills, and budgets remain out of
scope. The shared Gemini planner system prompt is operator-configurable separately.

## Trust boundaries

- Generated hypotheses are untrusted proposals. They are stored in browser
  `localStorage` until a user confirms them for one planning-cycle request.
- Confirmed hypotheses are validated against the current client disruption catalog,
  normalized by the client, and reconciled against the frozen client state.
- Browser-local hypotheses are not written to the platform signal database.
- Simulation metrics always come from the connected client.
- Single and panel planners propose qualitative interventions only. Client validation,
  intervention simulation, deterministic ranking, and human decisions remain outside
  the providers.

## Iterations

1. Add strict hypothesis-generation request/response contracts and deterministic and
   Gemini adapters.
2. Admit confirmed browser hypotheses into risk scenario generation through the same
   schema, target, normalization, and reconciliation checks as provider hypotheses.
3. Add a bounded stub panel that produces role-labelled alternatives through the
   existing `PlannerProvider` protocol.
4. Persist `single` or `panel` mode on each planning cycle and use it when baseline
   results are passed to planners.
5. Add UI controls for prompt generation, local review/removal, signal confirmation,
   explicit simulation, plan display, and plan approval/rejection.
6. Cover contracts, providers, service/API lifecycle, local-storage helpers, UI gates,
   lint, and strict TypeScript compilation.
