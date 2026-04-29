{ fossilsafe, inputs, pkgs }:
let
  inherit (pkgs) lib;
  system = pkgs.stdenv.hostPlatform.system;
  inherit (fossilsafe)
    frontendNpmDepsHash
    frontendPostPatch
    frontendSourceRoot
    pythonEnv
    src
    version
    ;

  mkFrontendCheck =
    name: command:
    pkgs.buildNpmPackage {
      pname = "fossilsafe-frontend-${name}";
      inherit src version;

      sourceRoot = frontendSourceRoot;
      npmDepsHash = frontendNpmDepsHash;
      postPatch = frontendPostPatch;

      buildPhase = ''
        runHook preBuild
        ${command}
        runHook postBuild
      '';

      installPhase = ''
        runHook preInstall
        mkdir -p "$out"
        printf '%s\n' ${lib.escapeShellArg name} > "$out/result"
        runHook postInstall
      '';
    };

  moduleEvalCheck =
    let
      evaluated = inputs.nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          ./fossilsafe-module.nix
          {
            system.stateVersion = "25.11";

            users.groups.tape = { };

            services.fossilsafe = {
              enable = true;
              package = fossilsafe;
              openFirewall = true;
              requireApiKey = true;
              stateDir = "/var/lib/fossilsafe-test";
              bootstrap = {
                settings = {
                  verification_enabled = true;
                };
              };
              settings = {
                tape = {
                  changer_device = "/dev/tape/by-id/REPLACE_ME";
                  drive_device = "/dev/tape/by-id/REPLACE_ME";
                  drive_devices = [
                    "/dev/tape/by-id/REPLACE_ME"
                    "/dev/tape/by-id/REPLACE_ME"
                  ];
                };
              };
            };
          }
        ];
      };

      configJson = evaluated.config.environment.etc."fossilsafe/config.json".source;
      execStartPre = builtins.concatStringsSep " " (evaluated.config.systemd.services.fossilsafe.serviceConfig.ExecStartPre or [ ]);
      assertionsHold =
        assert builtins.elem 5001 evaluated.config.networking.firewall.allowedTCPPorts;
        assert evaluated.config.users.users.fossilsafe.isSystemUser;
        assert builtins.elem "tape" evaluated.config.users.users.fossilsafe.extraGroups;
        assert builtins.elem "tape" evaluated.config.systemd.services.fossilsafe.serviceConfig.SupplementaryGroups;
        assert evaluated.config.systemd.services.fossilsafe.environment.FOSSILSAFE_REQUIRE_API_KEY == "true";
        assert builtins.any (rule: lib.hasInfix "/var/lib/fossilsafe-test/hooks.d" rule) evaluated.config.systemd.tmpfiles.rules;
        assert builtins.match ".*fossilsafe-bootstrap.*" execStartPre != null;
        true;
    in
    assert assertionsHold;
    pkgs.runCommand "fossilsafe-module-eval-check" {
      nativeBuildInputs = [ pkgs.jq ];
    } ''
      jq -e '.backend_port == 5001' ${configJson} >/dev/null
      jq -e '.diagnostics_dir == "/var/lib/fossilsafe-test/diagnostics"' ${configJson} >/dev/null
      jq -e '.tape.drive_devices == ["/dev/tape/by-id/REPLACE_ME", "/dev/tape/by-id/REPLACE_ME"]' ${configJson} >/dev/null
      touch "$out"
    '';
in
{
  package-build = fossilsafe;

  backend-pytest = pkgs.runCommand "fossilsafe-backend-pytest" {
    nativeBuildInputs = [ pythonEnv ];
  } ''
    export HOME="$TMPDIR/home"
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONPATH=${src}
    mkdir -p "$HOME"
    cd ${src}
    ${pythonEnv}/bin/pytest -ra -p no:cacheprovider backend/tests
    touch "$out"
  '';

  backend-ruff = pkgs.runCommand "fossilsafe-backend-ruff" {
    nativeBuildInputs = [ pkgs.ruff ];
  } ''
    export RUFF_CACHE_DIR="$TMPDIR/ruff-cache"
    mkdir -p "$RUFF_CACHE_DIR"
    cd ${src}
    ${pkgs.ruff}/bin/ruff check backend --select E9,F63,F7,F82
    touch "$out"
  '';

  frontend-lint = mkFrontendCheck "lint" "npm run lint";
  frontend-test = mkFrontendCheck "test" "npm run test -- --run";
  frontend-build = mkFrontendCheck "build" "npm run build";
  module-eval = moduleEvalCheck;
}
