# Experiment Instructions

Apply these rules to all experiments unless a deeper `AGENTS.md` says
otherwise.

- Keep unstable or prototype work isolated under `experiments/`.
- Put experiment changes in the experiment flake and experiment-local files.
- Do not wire experimental services or modules into `flake.nix`, host
  assemblies, or shared system roles until the experiment is declared stable.
- Promotion from `experiments/` to system-level modules must be an explicit,
  separate step.
- For experiment-local flake design, use the `nixos` skill and the `dendritic`
  skill appendix.
