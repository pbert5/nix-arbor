{ lib }:
let
  resolveRoleHomeNames = roles: roleNames:
    lib.unique (
      lib.concatMap
        (roleName: (roles.${roleName} or { }).homes or [ ])
        roleNames
    );

  resolveHomeModule = { homeRegistry, name }:
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
      homeNames = lib.unique (roleHomes ++ extraHomeNames ++ [ homeModuleName ]);
    in
    {
      imports = builtins.map
        (name: resolveHomeModule {
          inherit homeRegistry name;
        })
        homeNames;

      home.username = user.home.username;
      home.homeDirectory = user.home.directory;
      home.stateVersion = user.home.stateVersion;

      flakeTarget.path = lib.mkDefault (
        lib.attrByPath
          [ "org" "flakeTarget" "path" ]
          "${config.home.homeDirectory}/flake"
          user
      );
    };

  mkAuthorizedKeys = user:
    lib.optionals (user.nixos ? authorizedKeysFile) (
      builtins.filter
        (line: line != "")
        (lib.splitString "\n" (builtins.readFile user.nixos.authorizedKeysFile))
    );
in
rec {
  inherit resolveRoleHomeNames;

  mkHomeModule =
    {
      extraHomeNames ? [ ],
      homeRegistry,
      roles,
      roleNames ? user.roles or [ ],
      user,
      userName,
    }:
    mkHomeIdentityModule {
      inherit extraHomeNames homeRegistry user userName;
      roleHomes = resolveRoleHomeNames roles roleNames;
    };

  mkUserModule =
    {
      extraHomeNames ? [ ],
      homeRegistry,
      roles,
      roleNames ? user.roles or [ ],
      user,
      userName,
    }:
    { pkgs, ... }:
    let
      userConfig =
        {
          isNormalUser = true;
          extraGroups = user.nixos.extraGroups or [ ];
          home = user.home.directory;
          shell = builtins.getAttr (user.nixos.shellPackage or "bashInteractive") pkgs;
        }
        // lib.optionalAttrs (user.nixos ? hashedPassword) {
          hashedPassword = user.nixos.hashedPassword;
        }
        // lib.optionalAttrs (user.nixos ? authorizedKeysFile) {
          openssh.authorizedKeys.keys = mkAuthorizedKeys user;
        };
    in
    {
      users.users.${user.home.username} = userConfig;

      home-manager.users.${user.home.username}.imports = [
        (
          mkHomeIdentityModule {
            inherit extraHomeNames homeRegistry user userName;
            roleHomes = resolveRoleHomeNames roles roleNames;
          }
        )
      ];
    };

  publishNixosModules =
    {
      homeRegistry,
      roles,
      users,
    }:
    lib.mapAttrs'
      (userName: user: {
        name = "user-${userName}";
        value = mkUserModule {
          inherit homeRegistry roles user userName;
        };
      })
      users;
}
