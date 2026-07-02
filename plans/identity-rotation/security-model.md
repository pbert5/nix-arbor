# Rotation Security Model

Status: planned.

## Rotation Triggers

A rotation is required or strongly recommended when:

- a private key, token, recovery value, or reusable enrollment credential is
  known or suspected to have been copied;
- a person or guest loses access after having access to a host or secret;
- a host is lost, stolen, decommissioned, reassigned, or no longer trusted;
- a service credential was present on a compromised host;
- an encryption recipient must be removed and that recipient could retain old
  ciphertext;
- a provider revokes or invalidates a credential;
- an algorithm, key size, or provider policy changes;
- an operator initiates a planned cryptographic refresh.

Routine time-based rotation is optional unless a provider or policy requires
it. Rotation should have a reason, not exist as security theater.

## Exposure Evidence

The planned exposure calculation uses evidence in this order:

1. Explicit operator input such as `--exposed-host`, `--exposed-user`, or an
   exact fingerprint.
2. Registry identity events and private-delivery metadata.
3. Signed delivery and activation receipts proving that a host received a
   generation.
4. Declarative host, user, guest-access, and service inventory.
5. Leader-only encrypted ledger recipient lists.

The result is an operator-reviewable set of affected credentials with a reason
for every edge. Unknown exposure is reported, not silently treated as safe.

The first implementation should calculate host-level exposure. User and guest
removal detection can join `inventory/guest-access.nix` and host user
assignments to those host-level edges. More granular process-level exposure is
out of scope until the inventory can prove it.

## Exposure Closure

For a compromised host, include:

- private identity material installed on that host;
- host authentication and encryption keys;
- reusable enrollment or provider tokens readable on that host;
- secrets delivered to the host according to signed receipts;
- ciphertext-accessible secrets when the host possessed a matching decryption
  key;
- shared credentials used by the host that cannot be revoked per member.

Do not automatically include:

- another host's private key merely because its public key or address was
  visible;
- public registry content;
- identifiers that grant no authority;
- unrelated credentials held only by a leader.

When an age recipient is compromised, changing only the recipient key is
insufficient. Any retained ciphertext encrypted to the old recipient remains
decryptable, so the underlying delivered secrets must be considered for
rotation too.

## Service-Specific Rules

### Host age

Rotate the compromised host's age identity, remove the old recipient from new
encryption operations, and rotate secrets whose ciphertext the old identity
could decrypt. Host-age rotation retains the configured multi-leader
authorization threshold.

### SSH host identity

Rotate a host's SSH private host key if it may have been copied. Clients must
receive the new signed registry identity before treating the replacement as
trusted. User authentication keys need rotation only when their private keys
were present or exposed.

### Yggdrasil

Rotate the affected node's private key, which necessarily changes its public
key and address. Other nodes do not rotate merely because their public
addresses were visible.

### Tailscale

Revoke or expire the affected node and re-enroll it. Invalidate any exposed
reusable auth key or API token. Stable tailnet IP addresses are not themselves
secrets and do not require rotation unless a separate policy demands it.

### git-annex

A repository UUID or location description is an identifier, not a secret.
Rotate SSH keys, tokens, encryption keys, or remote credentials that grant
access. Remove or mark the old annex location unavailable when the machine is
retired.

### Radicle

Rotate the node signing identity only if its private key was exposed. Public
node IDs observed by a guest do not create exposure by themselves.

### IPNS and onion transports

IPNS names and onion addresses derive from private transport keys. Their
rotation is a trust-anchor and reachability handoff, not an ordinary service
identity update. A graceful transition must publish the new route through an
unaffected trusted route and update local policy before retiring the old one.
If the old transport key is compromised, require the existing leader-policy
authorization threshold rather than relying solely on a signature from that
old key.

## Graceful Versus Emergency Rotation

Graceful rotation is appropriate for planned retirement, routine refresh, and
access removal where compromise is not suspected:

1. Append the rotation intent.
2. Generate a higher-generation replacement.
3. Deliver and activate the replacement.
4. Collect signed acknowledgement evidence.
5. Deprecate the old generation.
6. Keep a bounded grace window if policy permits.
7. Burn the old fingerprint.

Emergency rotation is appropriate whenever continued use is unsafe:

1. Revoke provider-side credentials where possible.
2. Append an irreversible burn immediately.
3. Generate and deploy a replacement.
4. Restore reachability through unaffected transports.
5. Record nodes that missed the transition and require re-enrollment.

Emergency mode must never delay revocation while waiting for acknowledgements.

## Completion Policy

Graceful completion uses all of:

- a configured minimum acknowledgement threshold;
- required acknowledgements from named critical nodes, when configured;
- a deadline;
- an explicit list of unreachable or retired nodes excluded by the operator;
- proof that at least one unaffected registry transport remains available
  during a transport-key handoff.

The status output must distinguish:

- acknowledged;
- pending and reachable;
- unreachable;
- explicitly excluded;
- missed deadline and requires re-enrollment.
