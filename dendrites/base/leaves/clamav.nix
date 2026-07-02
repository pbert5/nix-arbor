{ ... }:
{
  systemd.tmpfiles.rules = [
    "d /var/lib/download-staging 0755 root root - -"
  ];

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
      scanDirectories = [
        "/home"
        "/etc"
        "/var/lib/download-staging"
        "/var/tmp"
      ];
    };

    clamonacc.enable = true;

    daemon.settings = {
      LocalSocketMode = "660";
      LogTime = true;
      ExtendedDetectionInfo = true;
      LogClean = false;
      LogVerbose = false;
      MaxThreads = 2;
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
    # Recursive scans encounter transient sockets and pipes under /home.
    # clamdscan reports those unsupported file types with exit code 2.
    SuccessExitStatus = [ 2 ];
  };
}
