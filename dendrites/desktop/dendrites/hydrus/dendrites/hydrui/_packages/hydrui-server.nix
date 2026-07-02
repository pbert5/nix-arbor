{
  buildGoModule,
  buildNpmPackage,
  fetchFromGitHub,
  lib,
  pkg-config,
  pixman,
  cairo,
  pango,
}:
let
  version = "0.9.0";
  src = fetchFromGitHub {
    owner = "hydrui";
    repo = "hydrui";
    rev = "v${version}";
    hash = "sha256-3oDzjuQXktkOUUVLaFGSEAtuO8TkxfXWEHnsZ1mJfUU=";
  };

  hydruiWww = buildNpmPackage {
    pname = "hydrui-www";
    inherit version src;

    VITE_HYDRUI_VERSION = version;
    npmDepsHash = "sha256-/tnGgnEAPke34SBTN/F0ZcSTdJPj6NpPsd8yuOwlRKQ=";

    nativeBuildInputs = [
      pkg-config
    ];

    buildInputs = [
      pixman
      cairo
      pango
    ];

    buildPhase = ''
      runHook preBuild

      npm run --workspaces build
      npm run --workspace web/hydrui-util pack

      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall

      mkdir -p $out/share/hydrui/internal/webdata
      cp internal/webdata/*.pack $out/share/hydrui/internal/webdata

      runHook postInstall
    '';
  };
in
buildGoModule {
  pname = "hydrui-server";
  inherit version src;

  subPackages = [
    "cmd/hydrui-server"
  ];

  preBuild = ''
    cp ${hydruiWww}/share/hydrui/internal/webdata/*.pack ./internal/webdata
  '';

  vendorHash = "sha256-gwCUhW+8UDYpHu4oUPdY8x/cJB84X+V6Imvl+Rq6PO0=";

  meta = {
    description = "Remote web UI for the hydrus network client";
    homepage = "https://hydrui.dev";
    license = lib.licenses.agpl3Only;
    mainProgram = "hydrui-server";
  };
}
