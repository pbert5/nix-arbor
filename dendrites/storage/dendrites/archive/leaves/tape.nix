{ lib, site, hostInventory, ... }:
let
  archiveOrg = lib.attrByPath [ "org" "storage" "annex" "archive" ] { } hostInventory;
  tapeOrg = archiveOrg.tape or { };
  tapeEnable = tapeOrg.enable or false;
in
lib.mkIf tapeEnable {
  # Tape archive integration defers to the storage/tape dendrite and
  # FossilSafe/LTFS fruit for device management.  This leaf enforces the
  # policy that tape is only reachable over the private overlay.
  assertions = [
    {
      assertion = builtins.elem "storage/tape" (hostInventory.dendrites or [ ]);
      message = ''
        Host enables archive tape backend but does not include the "storage/tape"
        dendrite.  Add "storage/tape" to the host's dendrites list.
      '';
    }
  ];
}
