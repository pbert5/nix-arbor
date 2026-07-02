{ lib }:
let
  addressOnly = cidr: lib.head (lib.splitString "/" cidr);

  directLinkInterfaces =
    { host, hosts }:
    let
      cfg = lib.attrByPath [ "org" "network" "directLink" ] null host;
    in
    lib.optionalAttrs (cfg != null) (
      let
        peerCfg = lib.attrByPath [ "org" "network" "directLink" ] null (hosts.${cfg.peer} or null);
      in
      {
        ${cfg.interfaceName} = {
          network = "direct-link";
          addresses = [ (addressOnly cfg.address) ];
          physicalConnections = lib.optional (peerCfg != null) {
            node = cfg.peer;
            interface = peerCfg.interfaceName;
          };
        };
      }
    );

  # Models a logical mesh overlay (Yggdrasil) whose per-node peer list is
  # declared explicitly in inventory/networks.nix, so the rendered graph
  # reflects actual configured peers rather than assuming full mesh.
  meshOverlayInterfaces =
    {
      hostName,
      host,
      networks,
      networkKey,
      networkId,
      ifNameDefault,
    }:
    let
      net = networks.${networkKey} or null;
      isMember = builtins.elem networkKey (host.networks or [ ]);
    in
    lib.optionalAttrs (net != null && isMember) (
      let
        nodes = net.nodes or { };
        hostNode = nodes.${hostName} or null;
        ifName = if hostNode == null then ifNameDefault else hostNode.ifName or (net.defaults.ifName or ifNameDefault);
      in
      lib.optionalAttrs (hostNode != null && ifName != "none") {
        ${ifName} = {
          network = networkId;
          virtual = true;
          addresses = lib.optional (hostNode ? address) hostNode.address;
          physicalConnections = builtins.map (peer: {
            node = peer;
            interface = ifName;
          }) (hostNode.peers or [ ]);
        };
      }
    );

  # Tailscale peers are dynamic (not individually declared), so membership
  # only groups hosts under the shared network rather than drawing edges.
  tailscaleInterface =
    { host }:
    lib.optionalAttrs (builtins.elem "tailscale" (host.networks or [ ])) {
      tailscale0 = {
        network = "tailscale";
        virtual = true;
      };
    };
in
{
  mkHostInterfaces =
    { hostName, host, inventory }:
    let
      networks = inventory.networks or { };
      hosts = inventory.hosts or { };
    in
    directLinkInterfaces { inherit host hosts; }
    // meshOverlayInterfaces {
      inherit hostName host networks;
      networkKey = "privateYggdrasil";
      networkId = "yggdrasil-private";
      ifNameDefault = "ygg0";
    }
    // meshOverlayInterfaces {
      inherit hostName host networks;
      networkKey = "publicYggdrasilPeering";
      networkId = "yggdrasil-public-peering";
      ifNameDefault = "none";
    }
    // tailscaleInterface { inherit host; };

  mkGlobalNetworks =
    { inventory }:
    let
      networks = inventory.networks or { };
      describe = key: default: (networks.${key} or { }).description or default;
    in
    {
      direct-link.name = "Direct link (point-to-point)";
      tailscale.name = describe "tailscale" "Tailscale";
      yggdrasil-private.name = describe "privateYggdrasil" "Yggdrasil (private overlay)";
      yggdrasil-public-peering.name = describe "publicYggdrasilPeering" "Yggdrasil (public peering)";
    };
}
