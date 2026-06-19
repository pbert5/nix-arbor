{
  name = "storage/bitlocker";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [
    "bitlocker-auto-unlock"
    "bitlocker-mounts"
  ];
  requires = [ "storage" ];
  conflicts = [ ];
}
