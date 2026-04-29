{
  name = "storage/git-annex";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "git-annex"
    "annex-repo-root"
    "annex-ssh-transfers"
  ];
  requires = [ "storage" ];
  conflicts = [ ];
  hostClasses = [
    "workstation"
    "compute-worker"
    "annex-client"
    "annex-storage"
  ];
}
