{
  name = "romm";
  kind = "fruit";
  maturity = "experimental";
  provides = [ "romm" ];
  requires = [ ];
  conflicts = [ ];
  requiresDendrites = [
    "media"
    "media/game-library/export"
  ];
  runtime = {
    kind = "service";
    backend = "podman";
  };
  persistent = true;
  ports = [ 8095 ];
}
