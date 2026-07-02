# Documentation Instructions

Apply these rules to documentation under `docs/`.

- When adding or changing a feature, component, flake output, inventory
  surface, or operational workflow, update the relevant docs in the same
  change.
- Prefer updating existing docs when they already cover the area.
- Add a new focused doc only when the feature needs usage notes, architecture
  notes, or operator guidance of its own.
- Do not leave implemented behavior documented only in plans, chat history, or
  code comments. Promote current truth into `docs/`.
- When a plan document becomes partially implemented, document the implemented
  subset clearly and label remaining items as planned rather than present fact.
- Keep docs aligned with the path-scoped `AGENTS.md` files. Do not recreate a
  separate agent-guideline hub under `docs/`.
