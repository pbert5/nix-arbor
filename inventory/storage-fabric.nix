{
  storageFabric = {
    enable = true;

    transport = {
      # Only private Yggdrasil is an approved content-transfer path.
      # Public IPv4/IPv6 is rejected by validation.
      privateNetwork = "privateYggdrasil";
      allowPublicContentTransfers = false;
    };

    annex = {
      repoRoot = "/srv/annex/cluster-data";
      user = "annex";
      group = "annex";
      defaultNumCopies = 2;
      # Repos used only for Git metadata (commits + annex tracking branch).
      # These must not be configured as content-transfer remotes.
      metadataRemotes = [
        "radicle"
        "github"
      ];

      # Preferred-content groups and their wanted expressions.
      # Hosts opt into a group via org.storage.annex.group in inventory.
      groups = {
        archive = {
          wanted = "standard or (include=*.important)";
          required = "standard";
        };
        hot = {
          wanted = "present and (not unused)";
          required = "";
        };
        compute = {
          wanted = "inallgroups";
          required = "";
        };
        workstation = {
          wanted = "present";
          required = "";
        };
        transient = {
          wanted = "nothing";
          required = "";
        };
      };
    };

    seaweedfs = {
      hotPool = {
        enable = true;
        # SeaweedFS replication strategy.
        # "001" keeps two copies across the current two seaweed-volume hosts.
        # Increase this only after adding enough seaweed-volume hosts.
        replication = "001";
        masterPort = 9333;
        filerPort = 8888;
        s3Port = 8333;
        volumePort = 8090;
        # Hot-pool staging mount point.
        mountPoint = "/hot";
        filerPath = "/srv/seaweedfs/filer";
        volumePath = "/srv/seaweedfs/volumes";
        # S3-compatible gateway.  Enable once SOPS/age credentials are configured.
        s3.enable = false;
      };
    };

    archive = {
      # Durable long-term remotes.  At least one must be enabled on any host
      # claiming the "archive-node" role.
      remotes = {
        tape = {
          enable = false;
          # Populated per-host via org.storage.annex.archive.tape.
        };
        nas = {
          enable = false;
          # Populated per-host via org.storage.annex.archive.nas.
        };
        object = {
          enable = false;
          # endpoint set per-host via org.storage.annex.archive.object.
        };
        removableDisk = {
          enable = false;
        };
      };

      # Drop-safety policy for archive remotes.
      # A file may only be dropped if this many independent archive copies exist.
      minArchiveCopies = 2;
    };

    radicle = {
      enable = false;
      # Seeds the flake repo and the annex metadata repo over private Ygg.
      # Does not transfer annex content.
      repos = [
        "flake-devbox"
        "cluster-data"
      ];
    };
  };
}
