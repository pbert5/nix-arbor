{
  inputs ? null,
}:
let
  users = import ./users.nix;
in
{
  hosts = import ./hosts.nix { inherit inputs; };
  guestAccess = import ./guest-access.nix;
  hostBootstrap = import ./host-bootstrap.nix;
  identities = import ./identity-services/identities.nix;
  identityPolicy = import ./identity-policy.nix;
  networks = import ./networks.nix;
  inherit users;
  people = users;
  ports = import ./ports.nix;
  storage = import ./storage/storage.nix;
  storageFabric = (import ./storage-fabric.nix).storageFabric;
} # TODO: something about this frustrates me, its literaly just a bunch of import logic, we should have dynamic import behavior to make this completely unnesesary
