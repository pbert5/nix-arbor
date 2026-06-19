let
  importedAt = "2026-01-01T00:00:00Z";
in
{
  "workstation-1" = {
    generation = 1;
    state = "active";
    sourceTimestamp = importedAt;
    public = {
      sshHostKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    };
  };

  "storage-1" = {
    generation = 1;
    state = "active";
    sourceTimestamp = importedAt;
    public = {
      sshHostKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";
    };
  };
}
