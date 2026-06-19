{ lib }:
let
  resolveHomeModule =
    { homeRegistry, name }:
    (homeRegistry.${name} or (throw "Missing home module '${name}' in dendritic registry.")).module;

  mkHomeIdentityModule =
    {
      extraHomeNames ? [ ],
      homeRegistry,
      roleHomes ? [ ],
      user,
      userName,
    }:
    {
      config,
      lib,
      ...
    }:
    let
      homeModuleName = user.home.homeModule or userName;
      userHomeNames = lib.attrByPath [ "org" "home" "sharedModules" ] [ ] user;
      homeNames = lib.unique (roleHomes ++ extraHomeNames ++ userHomeNames ++ [ homeModuleName ]);
    in
    {
      imports = builtins.map (
        name:
        resolveHomeModule {
          inherit homeRegistry name;
        }
      ) homeNames;

      home.username = user.home.username;
      home.homeDirectory = user.home.directory;
      home.stateVersion = user.home.stateVersion;

      flakeTarget.path = lib.mkDefault (
        lib.attrByPath [ "org" "flakeTarget" "path" ] "${config.home.homeDirectory}/flake" user
      );
    };

  readAuthorizedKeysFile =
    path:
    builtins.filter (line: line != "" && !(lib.hasPrefix "#" line)) (
      lib.splitString "\n" (builtins.readFile path)
    );

  mkAuthorizedKeys =
    user:
    let
      files =
        lib.optionals (user.nixos ? authorizedKeysFile) [ user.nixos.authorizedKeysFile ]
        ++ (user.nixos.authorizedKeysFiles or [ ]);
    in
    lib.unique ((user.nixos.authorizedKeys or [ ]) ++ lib.concatMap readAuthorizedKeysFile files);
in
rec {
  mkHomeModule =
    {
      extraHomeNames ? [ ],
      homeRegistry,
      user,
      userName,
    }:
    mkHomeIdentityModule {
      inherit
        extraHomeNames
        homeRegistry
        user
        userName
        ;
    };

  mkUserModule =
    {
      extraHomeNames ? [ ],
      homeRegistry,
      user,
      userName,
    }:
    { pkgs, ... }:
    let
      userConfig = {
        isNormalUser = true;
        extraGroups = user.nixos.extraGroups or [ ];
        home = user.home.directory;
        shell = builtins.getAttr (user.nixos.shellPackage or "bashInteractive") pkgs;
      }
      // lib.optionalAttrs (user.nixos ? hashedPassword) {
        hashedPassword = user.nixos.hashedPassword;
      }
      // lib.optionalAttrs (mkAuthorizedKeys user != [ ]) {
        openssh.authorizedKeys.keys = mkAuthorizedKeys user;
      };
    in
    {
      users.users.${user.home.username} = userConfig;

      home-manager.users.${user.home.username}.imports = [
        (mkHomeIdentityModule {
          inherit
            extraHomeNames
            homeRegistry
            user
            userName
            ;
        })
      ];
    };

  publishNixosModules =
    {
      homeRegistry,
      users,
    }:
    lib.mapAttrs' (userName: user: {
      name = "user-${userName}";
      value = mkUserModule {
        inherit homeRegistry user userName;
      };
    }) users;
}
