{
  name = "storage/git-annex";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "git-annex"
    "annex-repo-root"
    "annex-ssh-transfers"
    "annex-p2p-transfers"
  ];
  requires = [ "storage" ];
  conflicts = [ ];
  cheatsheets.fileRegex = "^cheats/.*\\.cheat$";
  identityRequirements = [
    {
      service = "git-annex";
      generator = "git-annex";
      sourceLedger = "inventory/identity-services/git-annex.nix";
    }
  ];
}
