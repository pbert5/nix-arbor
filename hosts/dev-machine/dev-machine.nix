{ ... }:
{
  imports = [ ./game-downloader-staging.nix ];

  networking.hostName = "dev-machine";
  boot.loader.grub.device = "/dev/sda";

  users.users.ash.uid = 1000;
  users.users.ash.linger = true;
  users.users.ash.extraGroups = [ "home-share" ];
  users.users.madeline.extraGroups = [ "home-share" ];

  systemd.tmpfiles.rules = [
    "z /home/example 2750 ash home-share - -"
    "z /home/example 2750 madeline home-share - -"
    "L+ /home/example/games - - - - /srv/games"
    "L+ /home/example/flake - - - - /work/flake"
    "L+ /home/example/games - - - - /srv/games"
  ];
}
