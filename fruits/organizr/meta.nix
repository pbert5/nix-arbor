{
  name = "organizr";
  kind = "fruit";
  maturity = "experimental";
  provides = [ "organizr" ];
  requires = [ ];
  conflicts = [ ];
  requiresDendrites = [ ];
  runtime = {
    kind = "service";
    backend = "podman";
  };
  persistent = true;
  ports = [ 9983 ];
}
