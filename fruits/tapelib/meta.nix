{
  name = "tapelib";
  kind = "fruit";
  maturity = "experimental";
  provides = [
    "tape-library-overlay"
    "tapelib"
  ];
  requires = [ ];
  conflicts = [ ];
  requiresDendrites = [ "storage/tape" ];
  runtime = {
    kind = "service";
  };
  persistent = true;
}
