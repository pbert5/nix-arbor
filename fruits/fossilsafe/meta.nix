{
  name = "fossilsafe";
  kind = "fruit";
  maturity = "experimental";
  provides = [
    "tape-backup-service"
    "fossilsafe"
  ];
  requires = [ ];
  conflicts = [ ]; #TODO: this is technicaly incompatible with yatm
  requiresDendrites = [ "storage/tape" ];
  runtime = {
    kind = "service";
  };
  persistent = true;
  ports = [ 5001 ];
}
