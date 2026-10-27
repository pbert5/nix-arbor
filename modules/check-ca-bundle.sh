set -eu
mkdir -p certs
rm -f certs/*
awk '/-----BEGIN (TRUSTED )?CERTIFICATE-----/ { n++; f = "certs/" n }
     f { print > f }
     /-----END (TRUSTED )?CERTIFICATE-----/ { close(f); f = "" }' "$1"
test -n "$(ls certs)"
for cert in certs/*; do
  fingerprint=$(openssl x509 -in "$cert" -noout -fingerprint -sha256)
  case "$fingerprint" in
    'sha256 Fingerprint=D7:A7:A0:FB:5D:7E:27:31:D7:71:E9:48:4E:BC:DE:F7:1D:5F:0C:3E:0A:29:48:78:2B:C8:3E:E0:EA:69:9E:F4'|    'sha256 Fingerprint=BC:4D:80:9B:15:18:9D:78:DB:3E:1D:8C:F4:F9:72:6A:79:5D:A1:64:3C:A5:F1:35:8E:1D:DB:0E:DC:0D:7E:B3'|    'sha256 Fingerprint=86:A1:EC:BA:08:9C:4A:8D:3B:BE:27:34:C6:12:BA:34:1D:81:3E:04:3C:F9:E8:A8:62:CD:5C:57:A3:6B:BE:6B'|    'sha256 Fingerprint=12:56:09:AA:30:1D:A0:A2:49:B9:7A:82:39:CB:6A:34:21:6F:44:DC:AC:9F:39:54:B1:42:92:F2:E8:C8:60:8F')
      trust=$(openssl x509 -in "$cert" -noout -text | sed -n '/^Trusted Uses:/,$p')
      echo "$trust" | grep -q '^Trusted Uses:$' || exit 1
      echo "$trust" | grep -q '^Rejected Uses:$' || exit 1
      trusted=$(echo "$trust" | sed -n '/^Trusted Uses:/,/^Rejected Uses:/p' | sed '1d;$d' | tr -d '[:space:]')
      test -z "$trusted" || exit 1
      rejected=$(printf '%s\n' "$trust" | awk '
        /^Rejected Uses:$/ { in_rejected = 1; next }
        in_rejected && /^[^[:space:]]/ { exit }
        in_rejected && NF {
          line = $0
          sub(/^[[:space:]]+/, "", line)
          sub(/[[:space:]]+$/, "", line)
          count = split(line, uses, /,[[:space:]]*/)
          for (i = 1; i <= count; i++) {
            sub(/^[[:space:]]+/, "", uses[i])
            sub(/[[:space:]]+$/, "", uses[i])
            print uses[i]
          }
        }')
      for usage in 'TLS Web Server Authentication' 'TLS Web Client Authentication' 'Code Signing' 'E-mail Protection' 'Time Stamping' 'IPSec End System' 'IPSec Tunnel' 'IPSec User'; do
        printf '%s\n' "$rejected" | grep -Fqx "$usage" || exit 1
      done
      ;;
  esac
done
