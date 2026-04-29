{ helpers, inputs, lib, usersLib, validation }:
let
  unstableOverlay = final: _prev: {
    unstable = import inputs.nixpkgs-unstable {
      inherit (final.stdenv.hostPlatform) system;
      config.allowUnfree = true;
    };
  };

  mkHomePkgs = { overlay, system }:
    import inputs.nixpkgs {
      inherit system;
      config.allowUnfree = true;
      overlays = [
        overlay
        unstableOverlay
      ];
    };

  resolveModule = { kind, registry, name }:
    (registry.${name} or (throw "Missing ${kind} '${name}' in dendritic registry.")).module;
in
rec {
  mkFruit = { fruitRegistry, name }:
    resolveModule {
      kind = "fruit";
      registry = fruitRegistry;
      inherit name;
    };

  mkHostDefinition =
    {
      genericSiteModule,
      host,
      hostName,
      inventory,
      registries,
      ...
    }:
    let
      fruitResolution = resolveFruits {
        fruitRegistry = registries.fruits;
        names = host.fruits or [ ];
      };

      resolvedDendrites = resolveDendrites {
        dendriteRegistry = registries.dendrites;
        names = (host.dendrites or [ ]) ++ fruitResolution.requiredDendrites;
      };

      compositionError = validation.assertComposition {
        dendriteRegistry = registries.dendrites;
        fruitRegistry = registries.fruits;
        inherit host hostName inventory;
        resolvedDendrites = resolvedDendrites;
        resolvedFruits = fruitResolution.names;
      };

      userModules =
        builtins.map
          (userName:
            usersLib.mkUserModule {
              extraHomeNames = host.roleHomes or [ ];
              homeRegistry = registries.homes;
              roles = inventory.roles;
              user = inventory.users.${userName} or (throw "Host '${hostName}' references unknown user '${userName}'.");
              inherit userName;
            })
          (host.users or [ ]);

      modules =
        [
          genericSiteModule
          {
            _module.args = {
              inherit inputs;
              dendritic = {
                inherit inventory registries;
              };
              hostInventory = host;
              hostName = hostName;
            };
          }
        ]
        ++ lib.optionals ((host.users or [ ]) != [ ]) [
          inputs.home-manager.nixosModules.home-manager
          {
            home-manager.extraSpecialArgs = {
              inherit inputs;
              site = inventory;
            };
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.backupFileExtension = "hm-bak";
          }
        ]
        ++ (host.hardwareModules or [ ])
        ++ builtins.map
          (name: resolveModule {
            kind = "dendrite";
            registry = registries.dendrites;
            inherit name;
          })
          resolvedDendrites
        ++ builtins.map
          (name: resolveModule {
            kind = "fruit";
            registry = registries.fruits;
            inherit name;
          })
          fruitResolution.names
        ++ builtins.map
          (name: resolveModule {
            kind = "host override";
            registry = registries.hosts;
            inherit name;
          })
          (host.overrides or [ ])
        ++ userModules;
    in
    builtins.seq compositionError {
      inherit compositionError modules resolvedDendrites;
      resolvedFruits = fruitResolution.names;
    };

  resolveDendrites =
    {
      dendriteRegistry,
      names,
    }:
    let
      visit = resolved: name:
        if builtins.elem name resolved then
          resolved
        else
          let
            entry = dendriteRegistry.${name} or (throw "Missing dendrite '${name}' in dendritic registry.");
            withRequirements = lib.foldl' visit resolved (entry.meta.requires or [ ]);
          in
          withRequirements ++ [ name ];
    in
    lib.foldl' visit [ ] (lib.unique names);

  resolveFruits =
    {
      fruitRegistry,
      names,
    }:
    let
      fruitNames = lib.unique names;
      requiredDendrites =
        lib.unique (
          lib.concatMap
            (name: ((fruitRegistry.${name} or (throw "Missing fruit '${name}' in dendritic registry.")).meta.requiresDendrites or [ ]))
            fruitNames
        );
    in
    {
      names = fruitNames;
      inherit requiredDendrites;
    };

  mkHost =
    {
      genericSiteModule,
      host,
      hostName,
      inventory,
      registries,
      ...
    }:
    let
      hostDefinition = mkHostDefinition {
        inherit genericSiteModule host hostName inventory registries;
      };
    in
    inputs.nixpkgs.lib.nixosSystem {
      inherit (host) system;
      modules = hostDefinition.modules;
    };

  mkHome =
    {
      genericSiteModule,
      inventory,
      overlay,
      registries,
      user,
      userName,
    }:
    inputs.home-manager.lib.homeManagerConfiguration {
      extraSpecialArgs = {
        inherit inputs;
        site = inventory;
      };
      modules = [
        genericSiteModule
        (
          usersLib.mkHomeModule {
            homeRegistry = registries.homes;
            roles = inventory.roles;
            inherit user userName;
          }
        )
      ];
      pkgs = mkHomePkgs {
        inherit overlay;
        system = user.system;
      };
    };

  mkNixosConfigurations =
    {
      genericSiteModule,
      inventory,
      registries,
    }:
    builtins.mapAttrs
      (hostName: host:
        mkHost {
          inherit genericSiteModule host hostName inventory registries;
        })
      (helpers.exportedHosts inventory);

  mkHomeConfigurations =
    {
      genericSiteModule,
      inventory,
      overlay,
      registries,
    }:
    builtins.mapAttrs
      (userName: user:
        mkHome {
          inherit genericSiteModule inventory overlay registries user userName;
        })
      inventory.users;
}
