{
  name = "network/radicle";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "radicle-node"
    "radicle-seed"
    "decentralized-git-mirror"
  ];
  requires = [ "network" ];
  conflicts = [ ];
  cheatsheets.fileRegex = "^cheats/.*\\.cheat$";
  identityRequirements = [
    {
      service = "radicle";
      generator = "radicle";
      sourceLedger = "inventory/identity-services/radicle.nix";
      targetPath = "/var/lib/radicle/keys/radicle";
      when = {
        path = [
          "org"
          "network"
          "radicle"
          "seed"
        ];
        equals = true;
      };
    }
  ];
}
