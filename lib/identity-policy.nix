{ }:
let
  registryPath = "/var/lib/cluster-identity/registry";

  leaderHostNames =
    hosts:
    builtins.filter (name: (hosts.${name}.org.clusterIdentity.role or "") == "leader") (
      builtins.attrNames hosts
    );

  deriveRemotes =
    { hosts, yggdrasilServices, bootstrapHosts }:
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
    { hosts, bootstrapHosts, leaderSigningKeysDir }:
    builtins.listToAttrs (
      builtins.map (
        hostName:
        let
          h = hosts.${hostName};
          signingKeyPath =
            h.org.clusterIdentity.registryTransport.identityFile or (
              bootstrapHosts.${hostName}.identityFile or null
            );
        in
        {
          name = hostName;
          value = {
            canWrite = true;
            publicSigningKey = builtins.readFile (leaderSigningKeysDir + "/${hostName}-root-deployer.txt");
            signingKeyPath = signingKeyPath;
          };
        }
      ) (leaderHostNames hosts)
    );

in
{
  normalizeIdentityPolicy =
    rawInventory:
    let
      rawPolicy = rawInventory.identityPolicy or { };
      hosts = rawInventory.hosts or { };
      yggdrasilServices = (rawInventory.identities or { }).services.yggdrasil or { };
      bootstrapHosts = rawInventory.hostBootstrap or { };
      leaderSigningKeysDir = rawPolicy.leaderSigningKeysDir or null;
    in
    rawPolicy
    // {
      registry = (rawPolicy.registry or { }) // {
        remotes = deriveRemotes { inherit hosts yggdrasilServices bootstrapHosts; };
      };
      leaders = deriveLeaders { inherit hosts bootstrapHosts leaderSigningKeysDir; };
    };
}
