# Home Manager Instructions

Apply these rules to Home Manager branches and per-user home modules under
`homes/`.

- Keep reusable Home Manager behavior under `homes/shared/`.
- Keep per-user modules under `homes/<user>/`.
- If a tool is configured only under `homes/` and has no owning dendrite,
  repo-local Navi coverage usually belongs in the catch-all `dendrites/dev-tools`
  cheatsheets because `homes/` is not scanned by `lib/cheatsheets.nix`.
- Build affected home configurations when a Home Manager change has enough risk
  to need evaluation.
- Do not use `default.nix`.
