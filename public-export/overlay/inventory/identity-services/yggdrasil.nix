let
  importedAt = "2026-01-01T00:00:00Z";
in
{
  "workstation-1" = {
    generation = 1;
    state = "active";
    sourceTimestamp = importedAt;
    importedAt = importedAt;
    public = {
      yggdrasilAddress = "200:db8::101";
      yggdrasilPublicKey = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
      deployHost = "200:db8::101";
    };
    private = {
      status = "not-yet-imported-to-encrypted-ledger";
      recipientHost = "workstation-1";
      targetPath = "/var/lib/yggdrasil/private.key";
    };
  };

  "storage-1" = {
    generation = 1;
    state = "active";
    sourceTimestamp = importedAt;
    importedAt = importedAt;
    public = {
      yggdrasilAddress = "200:db8::102";
      yggdrasilPublicKey = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
      deployHost = "200:db8::102";
    };
    private = {
      status = "not-yet-imported-to-encrypted-ledger";
      recipientHost = "storage-1";
      targetPath = "/var/lib/yggdrasil/private.key";
    };
  };
}
