{ lib, site, hostInventory, ... }:
let
  archiveOrg = lib.attrByPath [ "org" "storage" "annex" "archive" ] { } hostInventory;
  objectOrg = archiveOrg.object or { };
  objectEnable = objectOrg.enable or false;
  objectEndpoint = objectOrg.endpoint or null;
  transport = lib.attrByPath [ "storageFabric" "transport" ] { } site;
  allowPublic = transport.allowPublicContentTransfers or false;
in
lib.mkIf objectEnable {
  assertions = [
    {
      assertion = objectEndpoint != null;
      message = ''
        Host enables archive object backend but org.storage.annex.archive.object.endpoint
        is not set.  Provide an S3-compatible endpoint URL.
      '';
    }
    {
      # When public transfers are not allowed, require the endpoint to look
      # like a private-overlay address (ends in -ygg, .ygg, or .internal).
      assertion =
        allowPublic
        || objectEndpoint == null
        || lib.any (suffix: lib.hasSuffix suffix objectEndpoint) [
          "-ygg"
          ".ygg"
          ".internal"
          "localhost"
          "127.0.0.1"
          "::1"
        ];
      message = ''
        Archive object endpoint "${toString objectEndpoint}" does not look like a
        private-overlay address.  Only endpoints ending in -ygg, .ygg, or .internal
        are allowed unless storageFabric.transport.allowPublicContentTransfers = true.
      '';
    }
  ];
}
