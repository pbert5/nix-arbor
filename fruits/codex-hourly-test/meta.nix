{
  name = "codex-hourly-test";
  kind = "fruit";
  maturity = "experimental";
  provides = [ "codex-hourly-test" ];
  requires = [ ];
  conflicts = [ ];
  requiresDendrites = [ ];
  runtime = {
    kind = "timer";
    backend = "systemd";
  };
  persistent = false;
}
