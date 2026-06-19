{
  lib,
  python3Packages,
}:

python3Packages.buildPythonApplication {
  pname = "tapelib";
  version = "0.1.0";
  pyproject = true;
  dontUsePythonRemoveTestsDir = true;
  src = lib.cleanSourceWith {
    src = ../../../../../experiments/tapelib;
    filter =
      path: _type:
      let
        baseName = builtins.baseNameOf path;
      in
      !(builtins.elem baseName [
        ".git"
        ".pytest_cache"
        "__pycache__"
        "dist"
        "result"
      ]);
  };

  build-system = [
    python3Packages.hatchling
  ];

  nativeCheckInputs = [
    python3Packages.pytestCheckHook
  ];

  dependencies = [
    python3Packages.fusepy
  ];

  pythonImportsCheck = [ "tapelib" ];

  meta = {
    description = "Tape library overlay scaffold with queue-driven planning";
    homepage = "https://example.invalid/tapelib";
    mainProgram = "tapelib";
  };
}
