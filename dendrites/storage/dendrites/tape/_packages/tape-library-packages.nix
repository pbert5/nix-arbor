{
  lib,
  pkgs,
  ports ? { },
  driveDevices ? [ ],
}:

let
  normalizeEndpoint =
    defaultPort: value:
    if builtins.isAttrs value then
      value
      // {
        port = value.port or defaultPort;
      }
    else if builtins.isInt value then
      { port = value; }
    else
      { port = defaultPort; };
  changerDefault = pkgs.callPackage ./changer-default.nix { };
  ltfsOpen = pkgs.callPackage ./ltfs-open.nix { };
  tapelibPackage = pkgs.callPackage ./tapelib-package.nix { };
  tapeDefault = pkgs.callPackage ./tape-default.nix { configuredDrives = driveDevices; };
  tapeDefault1 = pkgs.callPackage ./tape-default.nix {
    configuredDrives = driveDevices;
    driveIndex = 0;
  };
  tapeDefault2 = pkgs.callPackage ./tape-default.nix {
    configuredDrives = driveDevices;
    driveIndex = 1;
  };
  yatmDebugPort = (normalizeEndpoint 8082 (ports.tapeLibraryYatmDebug or { })).port;
  yatmPort = (normalizeEndpoint 8081 (ports.tapeLibraryYatm or { })).port;
in
rec {
  inherit
    tapelibPackage
    changerDefault
    ltfsOpen
    tapeDefault
    tapeDefault2
    ;

  backupper = pkgs.callPackage ./backupper-control.nix { };

  backupperRunner = pkgs.callPackage ./backupper-runner.nix {
    inherit
      ltfsOpen
      tapelibPackage
      ;
    python3 = pkgs.python3;
  };

  ltfsDefault = pkgs.callPackage ./ltfs-default.nix {
    inherit lib tapeDefault;
  };

  ltfsDefault2 = pkgs.callPackage ./ltfs-default.nix {
    inherit lib;
    name = "ltfs-default-2";
    tapeDefault = tapeDefault2;
  };

  mtWithDefaults = pkgs.callPackage ./mt-with-defaults.nix {
    inherit lib tapeDefault;
  };

  mt1WithDefaults = pkgs.callPackage ./mt-with-defaults.nix {
    inherit lib;
    name = "mt1";
    tapeDefault = tapeDefault1;
  };

  mt2WithDefaults = pkgs.callPackage ./mt-with-defaults.nix {
    inherit lib;
    name = "mt2";
    tapeDefault = tapeDefault2;
  };

  mtxWithDefaults = pkgs.callPackage ./mtx-with-defaults.nix {
    inherit lib changerDefault;
  };

  stfs = pkgs.callPackage ./stfs.nix { };

  yatm = pkgs.callPackage ./yatm.nix {
    inherit
      lib
      pkgs
      tapeDefault
      ltfsOpen
      mtWithDefaults
      yatmDebugPort
      yatmPort
      ;
  };
}
