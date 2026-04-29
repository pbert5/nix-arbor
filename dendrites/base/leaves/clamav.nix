{ ... }:
{
  services.clamav = {
    daemon.enable = true;

    updater = {
      enable = true;
      frequency = 24;
      interval = "hourly";
    };

    scanner = {
      enable = true;
      interval = "*-*-* 03:30:00";
    };

    clamonacc.enable = true;

    daemon.settings = {
      LocalSocketMode = "660";
      LogTime = true;
      ExtendedDetectionInfo = true;
      LogClean = false;
      LogVerbose = false;
      OnAccessPrevention = true;
      OnAccessIncludePath = "/var/lib/download-staging";
      OnAccessExcludePath = "/nix/store";
    };
  };

  systemd.timers.clamdscan.timerConfig = {
    Persistent = true;
    RandomizedDelaySec = "45m";
  };

  systemd.services.clamdscan.serviceConfig = {
    Nice = 15;
    IOSchedulingClass = "idle";
  };
}
