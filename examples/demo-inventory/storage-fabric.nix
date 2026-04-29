{
  storageFabric = {
    enable = true;

    transport = {
      privateNetwork = "privateYggdrasil";
      allowPublicContentTransfers = false;
    };

    annex = {
      repoRoot = "/srv/annex/cluster-data";
      user = "annex";
      group = "annex";
      defaultNumCopies = 2;
      metadataRemotes = [
        "github"
      ];
      groups.archive = {
        wanted = "standard";
        required = "standard";
      };
    };

    seaweedfs.hotPool = {
      enable = true;
      replication = "000";
      masterPort = 9333;
      filerPort = 8888;
      s3Port = 8333;
      volumePort = 8090;
      mountPoint = "/hot";
      filerPath = "/srv/seaweedfs/filer";
      volumePath = "/srv/seaweedfs/volumes";
      s3.enable = false;
    };

    archive = {
      remotes.nas.enable = false;
      minArchiveCopies = 1;
    };
  };
}
