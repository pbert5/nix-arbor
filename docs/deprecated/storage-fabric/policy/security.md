# Storage Fabric Security

The security documentation moved into the split storage-fabric doc tree.

## Read the new pages

- security posture:
  [`storage-fabric/policy/security.md`](../../../storage-fabric/policy/security.md)
- validation rules that enforce parts of that posture:
  [`storage-fabric/policy/validation.md`](../../../storage-fabric/policy/validation.md)

The storage fabric remains private by default: annex content transfer,
SeaweedFS traffic, and Radicle seeding are meant to stay on the private Ygg
overlay unless the policy is changed deliberately.
