{ pi, pkgs }:
let
  sd = pi.config.sdImage;
  # Upstream boot helpers run ARM executables. Prepare their files on the
  # ARM builder; tar preserves boot file modes across the Nix store boundary.
  bootFiles = pi.pkgs.runCommand "raspberry-evolver-boot-files" { } ''
    mkdir -p files firmware "$out"
    ${sd.populateRootCommands}
    ${sd.populateFirmwareCommands}
    export TAR_OPTIONS="--sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner"
    tar -C files -cf "$out/root.tar" .
    tar -C firmware -cf "$out/firmware.tar" .
  '';
  nativeRoot = sd.rootFilesystemImage.override {
    inherit pkgs;
    inherit (pkgs)
      e2fsprogs
      libfaketime
      perl
      fakeroot
      zstd
      ;
    populateImageCommands = "tar -xf ${bootFiles}/root.tar -C files";
  };
  packed = pi.extendModules {
    modules = [
      {
        sdImage.rootFilesystemImage = nativeRoot;
        sdImage.populateFirmwareCommands = pkgs.lib.mkForce "tar -xf ${bootFiles}/firmware.tar -C firmware";
      }
    ];
  };
in
if pkgs.stdenv.buildPlatform.system == pi.pkgs.stdenv.hostPlatform.system then
  pi.config.system.build.sdImage
else
  packed.config.system.build.sdImage.override {
    inherit (pkgs)
      stdenv
      dosfstools
      e2fsprogs
      mtools
      libfaketime
      util-linux
      zstd
      ;
  }
