{ inputs ? null }:
let
  users = import ./users.nix;
in
{
  hosts = import ./hosts.nix { inherit inputs; };
  hostBootstrap = import ./host-bootstrap.nix;
  networks = import ./networks.nix;
  roles = import ./roles.nix;
  inherit users;
  people = users;
  ports = import ./ports.nix;
  storage = import ./storage.nix;
  storageFabric = (import ./storage-fabric.nix).storageFabric;
}#TODO: something about this frustrates me, its literaly just a bunch of import logic, we should have dynamic import behavior to make this completely unnesesary
