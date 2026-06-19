{
  storageFabric = {
    enable = false;

    transport = {
      privateNetwork = "privateYggdrasil";
      allowPublicContentTransfers = false;
    };

    annex = {
      repoRoot = "/srv/annex/cluster-data";
      user = "annex";
      group = "annex";
      defaultNumCopies = 2;
      metadataRemotes = [ "github" ];
    };

    archive = {
      minArchiveCopies = 1;
    };
  };
}
