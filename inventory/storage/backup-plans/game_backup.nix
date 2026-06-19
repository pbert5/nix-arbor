{
  enable = true;
  host = "t320-0";
  tool = "backupper";
  description = "Modern LTFS/LTO-5 game-library backup plan on t320-0.";
  state_dir = "/var/lib/backupper/game_backup";

  source_roots = [
    "/big/GameLibrary/_source-archives"
    "/big/GameLibrary/incoming"
  ];
  loose_roots = [ "/big/GameLibrary/roms" ];

  namespace_prefix = "/games";
  tape_capacity_bytes = 1200000000000;
  direct_source_write = true;
  catalog_loaded_tape_before_write = true;
  coverage_archive_roots = [
    "/big/GameLibrary/_source-archives"
    "/big/GameLibrary/incoming"
  ];
  coverage_zip_extensions = [ ".zip" ];
  coverage_fail_on_missing = false;
  coverage_max_missing_bytes = "10G";
  small_file_bundle_max_bytes = "0";

  # Keep the active rotation on tapes that are not currently showing unresolved
  # LTFS consistency or write-path failures. 383685L5 remains in rotation with
  # resumable partial data already on it. 430550L5 was recovered enough to
  # mount and accept a tiny probe write, but it failed again on the first
  # sustained LTFS archive write and is back out pending deeper media/drive
  # investigation. 385182L5 is also still excluded until it is recovered and
  # re-verified the same way.
  selected_tapes = [
    {
      barcode = "383685L5";
      drive = "drive0";
    }
    {
      barcode = "384933L5";
      drive = "drive1";
    }
    {
      barcode = "384333L5";
      drive = "drive0";
    }
    {
      barcode = "428857L5";
      drive = "drive0";
    }
    {
      barcode = "384337L5";
      drive = "drive1";
    }
    {
      barcode = "429414L5";
      drive = "drive0";
    }
    {
      barcode = "426578L5";
      drive = "drive1";
    }
    {
      barcode = "426397L5";
      drive = "drive1";
    }
  ];
}
