{ lib, site, ... }:
let
  fabric = site.storageFabric or { };
  transport = fabric.transport or { };
  allowPublic = transport.allowPublicContentTransfers or false;
  privateNetwork = transport.privateNetwork or "privateYggdrasil";
  privateYgg = lib.attrByPath [ "networks" privateNetwork ] { } site;
  yggIfName = lib.attrByPath [ "defaults" "ifName" ] "ygg0" privateYgg;
in
{
  # Assertion: public content transfers must be explicitly allowed.
  assertions = [
    {
      assertion = allowPublic == false;
      message = ''
        storageFabric.transport.allowPublicContentTransfers is true.
        Annex content transfers over public networks are not allowed in this
        configuration.  Set allowPublicContentTransfers = false or explicitly
        acknowledge the risk in your host override.
      '';
    }
  ];

  # Firewall: annex SSH port is not opened on public interfaces.
  # The openssh service itself restricts the annex user to git-annex-shell.
  # No additional port rules are needed here; see seaweedfs-hot/leaves/firewall.nix
  # for SeaweedFS port rules.
}
