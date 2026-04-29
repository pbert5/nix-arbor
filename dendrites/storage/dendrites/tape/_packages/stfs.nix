{
  lib,
  buildGoModule,
  fetchFromGitHub,
}:

buildGoModule rec {
  pname = "stfs";
  version = "0.1.1";

  src = fetchFromGitHub {
    owner = "pojntfx";
    repo = "stfs";
    rev = "v${version}";
    hash = "sha256-2dl7VK3mwasusNLiLfNVNjaNSEKo+eKyFwOwUDL9RzA=";
  };

  vendorHash = "sha256-uyW1k5pJpSOlVJ6bDxEM/nQYGdrw0Inbdh4PGgNl5go=";

  subPackages = [ "cmd/stfs" ];

  ldflags = [
    "-s"
    "-w"
  ];

  doCheck = false;

  meta = {
    description = "Simple Tape File System for tape drives and tar files";
    homepage = "https://github.com/pojntfx/stfs";
    license = lib.licenses.agpl3Only;
    mainProgram = "stfs";
    platforms = lib.platforms.linux;
  };
}
