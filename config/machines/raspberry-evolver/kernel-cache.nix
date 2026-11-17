# Fetch the two reference-free outputs of the upstream Pi 4 kernel. These
# NarHashes come from its signed Cachix narinfos. Nix verifies the unpacked
# contents on any builder without changing the builder's trusted keys.
{
  lib,
  nixos-raspberrypi,
  pkgs,
  ...
}:
let
  upstream = nixos-raspberrypi.packages.${pkgs.stdenv.hostPlatform.system}.linuxPackages_rpi4;
  kernelName = "linux_rpi-bcm2711-6.18.59-unstable_20261026";
  fetch =
    name: archive: sha256:
    import <nix/fetchurl.nix> {
      inherit name sha256;
      url = "https://nixos-raspberrypi.cachix.org/nar/${archive}.nar.xz";
      unpack = true;
    };
  out =
    fetch kernelName "20633cd7-6bfe-44ed-9549-7607dd520448"
      "07d0h19vksxfr87ia8nawq6ddqaf06iwwhb3q6pip1brwh09qqcr";
  modules =
    fetch "${kernelName}-modules" "618baedd-11bb-46fb-a7ea-42279199a62f"
      "0xbrahbml6w84il2jqnblimragmxcwb5jq0mykfbwx4slgp9a4ih";
  cachedKernel =
    kernel:
    if builtins.baseNameOf kernel.outPath == "izg2jbq7bv1c8mqqymc87l3mby727smq-${kernelName}" then
      kernel
      // {
        inherit out modules;
        inherit (out) outPath;
        # NixOS applies configured patches via kernel.override. Compare the
        # resulting upstream identity again before using any cached bytes.
        override = args: cachedKernel (kernel.override args);
      }
    else
      lib.warn "raspberry-evolver: upstream kernel changed; using the source build until the signed cache pins are refreshed" kernel;
in
{
  boot.kernelPackages = upstream.extend (_final: prev: { kernel = cachedKernel prev.kernel; });
}
