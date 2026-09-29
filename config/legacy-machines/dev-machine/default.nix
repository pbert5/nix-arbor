{
  system = "x86_64-linux";
  hostname = "dev-machine";
  profiles = [ ];
  state = "suspended";
  identity = {
    id = "dev-machine";
    aliases = [ ];
  };
  metadata.migration = {
    disposition = "template-only";
    source = "references/flake-devbox/src/hosts/dev-machine/dev-machine.nix";
    reason = "Generic development template, not a stable machine identity; no legacy users, links, or services are ported.";
  };
}
