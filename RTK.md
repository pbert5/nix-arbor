# RTK

RTK may be used as an optional, read-oriented output filter during development.
Repository policy remains authoritative in `AGENTS.md`; RTK does not replace
its worktree, review, or destructive-action rules.

Prefer `rtk read`, `rtk git`, and `rtk err` when their compact output helps.
Use native commands when exact or complete output matters. Do not run
`rtk init`: installing user-level hooks is not part of repository setup.
