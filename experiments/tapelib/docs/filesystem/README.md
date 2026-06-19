# Tapelib Filesystem

The tapelib FUSE mount is a virtual control and catalog surface. Normal
navigation should feel like browsing a small local filesystem. Physical tape
movement is only expected when an operation explicitly asks for hardware state,
queues a retrieve, or a separate queue runner executes tape work.

Focused docs:

- [Operation Matrix](./operations.md)
- [Performance Smoke Test](./performance-smoke-test.md)

Useful commands:

```bash
tapelib filesystem-smoke-test
tapelib filesystem-smoke-test --fail-slow
tapelib filesystem-smoke-test --include-hardware
```

The default smoke test is side-effect-free. It does not open archived readable
files, does not write to the inbox, and does not read live changer inventory.
