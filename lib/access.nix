{ helpers, lib }:
let
  cleanList = values:
    lib.unique (
      builtins.filter (value: value != null && value != "") values
    );

  selectorToList =
    universe: selector:
    if selector == "all" then
      universe
    else if selector == "none" || selector == null then
      [ ]
    else if builtins.isList selector then
      selector
    else
      [ selector ];

  normalizeGuest =
    guestName: guest:
    let
      ssh = guest.ssh or { };
      yggdrasil = guest.yggdrasil or { };
    in
    guest
    // {
      name = guest.name or guestName;
      ssh = ssh // {
        authorizedKeys = cleanList ((ssh.authorizedKeys or [ ]) ++ (guest.sshKeys or [ ]));
      };
      inherit yggdrasil;
    };

  guestNamesFromGrant =
    grant:
    cleanList ((grant.guests or [ ]) ++ lib.optional (grant ? guest) grant.guest);

  guestKeys =
    guests: guestNames:
    lib.concatMap (guestName: lib.attrByPath [ guestName "ssh" "authorizedKeys" ] [ ] guests) guestNames;

  grantKeys =
    guests: grant:
    cleanList ((grant.keys or [ ]) ++ (grant.authorizedKeys or [ ]) ++ guestKeys guests (guestNamesFromGrant grant));

  resolveUserName =
    users: userName:
    if userName == "root" then
      "root"
    else if users ? ${userName} then
      users.${userName}.home.username or userName
    else
      userName;

  hostUserNames =
    users: host:
    builtins.map (userName: resolveUserName users userName) (host.users or [ ]);

  allowedUserNames = users: host: [ "root" ] ++ hostUserNames users host;

  requestedUserNames =
    users: host: selector:
    if selector == "all" then
      hostUserNames users host
    else
      builtins.map (resolveUserName users) (selectorToList [ ] selector);

  normalizeSshGrant =
    {
      guests,
      hostNames,
      hosts,
      users,
    }:
    grantName: grant:
    let
      targetHosts = selectorToList hostNames (grant.hosts or "none");
      guestNames = guestNamesFromGrant grant;
      targetUsersByHost = builtins.listToAttrs (
        builtins.map
          (hostName:
            let
              host = hosts.${hostName} or { users = [ ]; };
              requested = requestedUserNames users host (grant.users or "none");
              allowed = allowedUserNames users host;
            in
            {
              name = hostName;
              value = builtins.filter (userName: builtins.elem userName allowed) requested;
            })
          targetHosts
      );
      missingUsersByHost = builtins.listToAttrs (
        builtins.map
          (hostName:
            let
              host = hosts.${hostName} or { users = [ ]; };
              requested = requestedUserNames users host (grant.users or "none");
              allowed = allowedUserNames users host;
            in
            {
              name = hostName;
              value = helpers.missingFrom allowed requested;
            })
          targetHosts
      );
    in
    grant
    // {
      name = grant.name or grantName;
      hosts = targetHosts;
      keys = grantKeys guests grant;
      guests = guestNames;
      missingGuestNames = helpers.missingFrom (builtins.attrNames guests) guestNames;
      inherit missingUsersByHost targetUsersByHost;
    };

  normalizeYggTrustedGuest =
    {
      guests,
      hostNames,
    }:
    ruleName: rawRule:
    let
      rule = if rawRule == true then { guest = ruleName; } else rawRule;
      guestName = rule.guest or ruleName;
      guest = guests.${guestName} or { };
      guestYgg = guest.yggdrasil or { };
      publicKey = rule.publicKey or guestYgg.publicKey or null;
      address = rule.address or guestYgg.address or null;
      aliases = rule.aliases or guestYgg.aliases or [ "${guestName}-ygg" ];
    in
    rule
    // {
      name = rule.name or ruleName;
      guest = guestName;
      guests = [ guestName ];
      hosts = selectorToList hostNames (rule.hosts or "all");
      inherit
        address
        aliases
        publicKey
        ;
      missingGuestNames = helpers.missingFrom (builtins.attrNames guests) [ guestName ];
    };

  yggByHost =
    hostNames: trustedGuests:
    lib.genAttrs hostNames (
      hostName:
      let
        rules = builtins.filter (rule: builtins.elem hostName (rule.hosts or [ ])) (
          builtins.attrValues trustedGuests
        );
        rulesWithPublicKeys = builtins.filter (rule: rule.publicKey != null) rules;
        rulesWithAddresses = builtins.filter (rule: rule.address != null) rules;
      in
      {
        guests = builtins.listToAttrs (
          builtins.map (rule: {
            name = rule.guest;
            value = {
              inherit (rule)
                address
                aliases
                publicKey
                ;
            };
          }) rules
        );
        publicKeys = cleanList (builtins.map (rule: rule.publicKey) rulesWithPublicKeys);
        sourceAddresses = cleanList (builtins.map (rule: rule.address) rulesWithAddresses);
      }
    );

  sshByHostUser =
    hostNames: sshGrants:
    lib.genAttrs hostNames (
      hostName:
      let
        grants = builtins.filter (grant: builtins.elem hostName (grant.hosts or [ ])) (
          builtins.attrValues sshGrants
        );
        targetUsers = cleanList (
          lib.concatMap (grant: grant.targetUsersByHost.${hostName} or [ ]) grants
        );
      in
      lib.genAttrs targetUsers (
        userName:
        cleanList (
          lib.concatMap (
            grant:
            if builtins.elem userName (grant.targetUsersByHost.${hostName} or [ ]) then
              grant.keys
            else
              [ ]
          ) grants
        )
      )
    );
in
{
  normalizeGuestAccess =
    {
      hosts,
      rawAccess,
      users,
    }:
    let
      hostNames = builtins.attrNames hosts;
      guests = lib.mapAttrs normalizeGuest (rawAccess.guests or { });
      sshGrants = lib.mapAttrs (
        normalizeSshGrant {
          inherit
            guests
            hostNames
            hosts
            users
            ;
        }
      ) (lib.attrByPath [ "ssh" "grants" ] { } rawAccess);
      trustedYggGuests = lib.mapAttrs (
        normalizeYggTrustedGuest {
          inherit guests hostNames;
        }
      ) (lib.attrByPath [ "yggdrasil" "trustedGuests" ] { } rawAccess);
    in
    rawAccess
    // {
      inherit guests;
      ssh = (rawAccess.ssh or { }) // {
        grants = sshGrants;
        byHostUser = sshByHostUser hostNames sshGrants;
      };
      yggdrasil = (rawAccess.yggdrasil or { }) // {
        trustedGuests = trustedYggGuests;
        byHost = yggByHost hostNames trustedYggGuests;
      };
    };
}
