# Experiment Isolation

All files under `experiments/` are unstable or prototype work.

- Changes must live in the experiment flake and experiment-local files only.
- Do **not** wire experimental services or modules into `flake.nix`, host
  assemblies, or shared system roles until the experiment is declared stable.
- Promotion from `experiments/` to system-level modules is an explicit,
  separate step — never do it silently as part of the experiment's own work.
