{ lib }:
let
  registryPath = "/var/lib/cluster-identity/registry";
  normalizePublicKey = path: lib.strings.trim (builtins.readFile path);

  leaderHostNames =
    hosts:
    builtins.filter (name: (hosts.${name}.org.clusterIdentity.role or "") == "leader") (
      builtins.attrNames hosts
    );

  deriveRemotes =
    {
      hosts,
      yggdrasilServices,
      bootstrapHosts,
    }:
    builtins.foldl' (
      acc: hostName:
      let
        yggAddress = yggdrasilServices.${hostName}.public.yggdrasilAddress or null;
        fallbackIp = bootstrapHosts.${hostName}.targetHost or null;
      in
      acc
      // (
        if yggAddress != null then
          {
            "leader-${hostName}-ygg" = {
              url = "ssh://root@[${yggAddress}]${registryPath}";
              fetch = true;
              push = true;
            };
          }
        else
          { }
      )
      // (
        if fallbackIp != null then
          {
            "leader-${hostName}-fallback" = {
              url = "ssh://root@${fallbackIp}${registryPath}";
              fetch = true;
              push = true;
            };
          }
        else
          { }
      )
    ) { } (leaderHostNames hosts);

  deriveLeaders =
    {
      hosts,
      bootstrapHosts,
      ipnsPublisherServices,
      onionMirrorServices,
      leaderSigningKeysDir,
    }:
    builtins.listToAttrs (
      builtins.map (
        hostName:
        let
          h = hosts.${hostName};
          ipnsRecord = ipnsPublisherServices.${hostName} or { };
          onionRecord = onionMirrorServices.${hostName} or { };
          onionPublic = onionRecord.public or { };
          onionUrl =
            onionPublic.onionUrl or (
              if (onionPublic.onionAddress or null) != null then "http://${onionPublic.onionAddress}" else null
            );
          signingKeyPath =
            h.org.clusterIdentity.signingKeyPath or (h.org.clusterIdentity.registryTransport.identityFile
              or (bootstrapHosts.${hostName}.identityFile or null)
            );
        in
        {
          name = hostName;
          value = {
            canWrite = true;
            publicSigningKey = normalizePublicKey (leaderSigningKeysDir + "/${hostName}-root-deployer.txt");
            signingKeyPath = signingKeyPath;
            ipnsName = ipnsRecord.public.ipnsName or (h.org.clusterIdentity.ipnsName or null);
            onionMirror = if onionUrl != null then onionUrl else (h.org.clusterIdentity.onionMirror or null);
            onionServicePublicKey = onionPublic.publicKeyFileBase64 or null;
          };
        }
      ) (leaderHostNames hosts)
    );

  deriveStatusPublishers =
    { statusIpnsServices, sshHostServices }:
    lib.mapAttrs (
      hostName: record:
      let
        public = record.public or { };
        sshPublic = (sshHostServices.${hostName} or { }).public or { };
      in
      {
        ipnsName = public.ipnsName or null;
        keyName = public.keyName or "cluster-identity-status-${hostName}";
        publicSigningKey = sshPublic.sshHostKey or null;
      }
    ) statusIpnsServices;

in
{
  normalizeIdentityPolicy =
    rawInventory:
    let
      rawPolicy = rawInventory.identityPolicy or { };
      hosts = rawInventory.hosts or { };
      yggdrasilServices = (rawInventory.identities or { }).services.yggdrasil or { };
      ipnsPublisherServices = (rawInventory.identities or { }).services.ipns-publisher or { };
      onionMirrorServices = (rawInventory.identities or { }).services.onion-mirror or { };
      statusIpnsServices = (rawInventory.identities or { }).services.status-ipns or { };
      sshHostServices = (rawInventory.identities or { }).services.ssh-host or { };
      bootstrapHosts = rawInventory.hostBootstrap or { };
      leaderSigningKeysDir = rawPolicy.leaderSigningKeysDir or null;
    in
    rawPolicy
    // {
      registry = (rawPolicy.registry or { }) // {
        remotes = deriveRemotes { inherit hosts yggdrasilServices bootstrapHosts; };
      };
      leaders = deriveLeaders {
        inherit
          hosts
          bootstrapHosts
          ipnsPublisherServices
          onionMirrorServices
          leaderSigningKeysDir
          ;
      };
      statusPublishers = deriveStatusPublishers {
        inherit statusIpnsServices sshHostServices;
      };
    };
}
