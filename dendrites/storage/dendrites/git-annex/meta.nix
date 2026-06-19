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
}
