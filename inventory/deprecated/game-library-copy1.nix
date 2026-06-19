{
  enable = true;
  host = "t320-0";
  tool = "game-backuper";
  description = "First full LTO-4 copy of the t320-local game library.";
  experiment_root = "/var/lib/game-backuper/game-library-copy1";

  library = {
    changer_device = null;
    drive_device = "/dev/tape/by-id/REPLACE_ME";
    drive_devices = [
      "/dev/tape/by-id/REPLACE_ME"
      "/dev/tape/by-id/REPLACE_ME"
    ];
    tape_generation = "LTO-4";
    native_capacity_gib = 800;
    usable_capacity_gib = 700;
    hard_capacity_gib = 750;
  };

  sources = {
    archive_roots = [
      "/big/GameLibrary/_source-archives"
      "/big/GameLibrary/incoming"
    ];
    loose_roots = [ "/big/GameLibrary/roms" ];
    archive_extensions = [
      ".zip"
      ".7z"
      ".rar"
      ".iso"
      ".chd"
      ".pkg"
      ".bin"
      ".cue"
      ".gz"
    ];
    zip_inventory_extensions = [ ".zip" ];
    exclude_extensions = [
      ".part"
      ".csv"
      ".json"
      ".md"
    ];
    ignore_names = [ "checksums.sha256" ];
  };

  planning = {
    target_archive_gib = 120;
    min_archive_gib = 50;
    max_archive_gib = 200;
    floor_archive_gib = 20;
    checkpoint_every_data_archives = 2;
    group_merge_floor_gib = 20;
  };

  tapes = [
    {
      volume_tag = "000004L4";
      slot = 4;
      drive_index = 0;
    }
    {
      volume_tag = "000005L4";
      slot = 5;
      drive_index = 1;
    }
    {
      volume_tag = "000006L4";
      slot = 6;
      drive_index = 0;
    }
    {
      volume_tag = "000007L4";
      slot = 7;
      drive_index = 1;
    }
    {
      volume_tag = "000008L4";
      slot = 8;
      drive_index = 0;
    }
    {
      volume_tag = "000009L4";
      slot = 9;
      drive_index = 1;
    }
  ];

  spool = {
    root = "/var/lib/game-backuper/game-library-copy1/spool";
    fallback_to_local_spool = false;
    max_parallel_staged_archives = 1;
    reserve_free_gib = 20;
  };

  verification = {
    direct_stream_sample_mib = 256;
    minimum_direct_stream_mib_per_s = null;
    calibration_file = "/var/lib/game-backuper/game-library-copy1/direct-stream-calibration.json";
    checksum_mode = "deferred";
  };

  catalog = {
    sqlite_path = "/var/lib/game-backuper/game-library-copy1/catalog.sqlite";
    snapshot_directory = "/var/lib/game-backuper/game-library-copy1/catalog-snapshots";
    plan_directory = "/var/lib/game-backuper/game-library-copy1/plans";
  };

  runtime = {
    backend = "live";
    write_mode = "direct";
    simulation_directory = "/var/lib/game-backuper/game-library-copy1/simulated-tapes";
    allow_live_tape_operations = true;
  };
}
