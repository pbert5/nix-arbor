{ }:
let
  fromRecord =
    record:
    let
      public = record.public or { };
      sourceTimestamp = record.sourceTimestamp or record.keyGeneratedAt or null;
    in
    {
      address = public.yggdrasilAddress or null;
      publicKey = public.yggdrasilPublicKey or null;
    }
    // (if sourceTimestamp == null then { } else { keyGeneratedAt = sourceTimestamp; });

in
{
  # Produces { hostName = { address, publicKey, ?keyGeneratedAt }; }
  # from raw identity-services yggdrasil service records.
  deriveYggdrasilIdentities =
    yggdrasilServices: builtins.mapAttrs (_hostName: record: fromRecord record) yggdrasilServices;
}
