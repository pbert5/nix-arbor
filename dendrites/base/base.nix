{ ... }:
{
  imports = [
    ./leaves/system.nix
    ./leaves/boot-grub.nix
    ./leaves/nix-maintenance.nix
    ./leaves/services.nix
    ./leaves/terminal.nix
    ./leaves/clamav.nix
  ];
}
