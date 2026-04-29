{
  name = "storage-observability";
  description = "Storage fabric health: annex copy-safety checks, SeaweedFS volume status, and Radicle seed status via CLI and systemd health units.";
  dendrite = "storage/storage-observability";
  requiredFacts = [ ];
  optionalFacts = [ "org.storage.annex" "org.network.radicle" ];
}
