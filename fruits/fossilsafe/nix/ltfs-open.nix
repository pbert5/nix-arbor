{
  lib,
  stdenv,
  fetchFromGitHub,
  autoreconfHook,
  pkg-config,
  fuse,
  icu,
  libxml2,
  libuuid,
  net-snmp,
}:

stdenv.mkDerivation rec {
  pname = "ltfs-open";
  version = "2.4.8.2-10520";

  src = fetchFromGitHub {
    owner = "LinearTapeFileSystem";
    repo = "ltfs";
    rev = "v${version}";
    hash = "sha256-1+oJyv5FrKc1GkPhARkv+w7CDrW1M8LKRK5Rb6pej5I=";
  };

  nativeBuildInputs = [
    autoreconfHook
    pkg-config
  ];

  buildInputs = [
    fuse
    icu
    libxml2
    libuuid
    net-snmp
  ];

  configureFlags = [
    "--disable-snmp"
  ];

  postPatch = ''
    substituteInPlace configure.ac \
      --replace-fail "2.4.5.1 (Prelim)" "${version}"
  '';

  preConfigure = ''
    mkdir -p .nix-bin

    cat > .nix-bin/pkgdata <<PKGDATA
    #!${stdenv.shell}
    exec ${icu.dev}/bin/pkgdata -O ${icu.dev}/lib/icu/${icu.version}/pkgdata.inc "\$@"
    PKGDATA

    chmod +x .nix-bin/pkgdata
    export PATH="$PWD/.nix-bin:$PATH"
    export ICU_MODULE_CFLAGS="$(${pkg-config}/bin/pkg-config --cflags icu-i18n)"
    export ICU_MODULE_LIBS="$(${pkg-config}/bin/pkg-config --libs icu-i18n)"
  '';

  enableParallelBuilding = true;

  meta = {
    description = "Reference LTFS implementation with IBM LTO drive support";
    homepage = "https://github.com/LinearTapeFileSystem/ltfs";
    license = lib.licenses.bsd3;
    mainProgram = "ltfs";
    platforms = lib.platforms.linux;
  };
}
