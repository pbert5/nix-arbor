{ ... }:
{
  services.sunshine = {
    enable = true;
    openFirewall = true;
    capSysAdmin = true;
    settings = {
      sunshine_name = "desktoptoodle";
      key_rightalt_to_key_win = "enabled";
    };
  };
}
