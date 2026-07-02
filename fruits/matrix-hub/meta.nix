{
  name = "matrix-hub";
  kind = "fruit";
  maturity = "experimental";
  provides = [ "matrix-hub" ];
  requires = [ ];
  conflicts = [ ];
  requiresDendrites = [ ];
  runtime = {
    kind = "service";
    backend = "systemd";
  };
  persistent = true;
  ports = [ 6167 ];
  cheatsheets.fileRegex = "^cheats/.*\\.cheat$";
}
