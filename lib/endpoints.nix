{ lib }:
let
  defaultAllowedCidrs = [
    "127.0.0.1/32"
    "100.64.0.0/10"
  ];

  normalizeEndpoint =
    defaultPort: value:
    let
      raw =
        if builtins.isAttrs value then
          value
        else if builtins.isInt value then
          { port = value; }
        else
          { };

      port = raw.port or defaultPort;
    in
    {
      allowedCidrs = raw.allowedCidrs or defaultAllowedCidrs;
      bind = raw.bind or "127.0.0.1";
      hosts = raw.hosts or [
        "127.0.0.1"
        "localhost"
      ];
      port = port;
      url = raw.url or "http://${raw.bind or "127.0.0.1"}:${toString port}";
    }
    // (builtins.removeAttrs raw [
      "allowedCidrs"
      "bind"
      "hosts"
      "port"
      "url"
    ]);

  portOf = defaultPort: value: (normalizeEndpoint defaultPort value).port;
in
{
  inherit normalizeEndpoint portOf;
}
