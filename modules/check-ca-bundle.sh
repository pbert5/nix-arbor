set -eu
mkdir -p certs
rm -f certs/*
awk '/-----BEGIN (TRUSTED )?CERTIFICATE-----/ { n++; f = "certs/" n }
     f { print > f }
     /-----END (TRUSTED )?CERTIFICATE-----/ { close(f); f = "" }' "$1"
test -n "$(ls certs)"
for cert in certs/*; do
  fingerprint=$(openssl x509 -in "$cert" -noout -fingerprint -sha256)
  if [ "$fingerprint" = "sha256 Fingerprint=D7:A7:A0:FB:5D:7E:27:31:D7:71:E9:48:4E:BC:DE:F7:1D:5F:0C:3E:0A:29:48:78:2B:C8:3E:E0:EA:69:9E:F4" ]; then
    trust=$(openssl x509 -in "$cert" -noout -text | sed -n '/^Trusted Uses:/,$p')
    echo "$trust" | grep -q '^Trusted Uses:$' || exit 1
    echo "$trust" | grep -q '^Rejected Uses:$' || exit 1
    trusted=$(echo "$trust" | sed -n '/^Trusted Uses:/,/^Rejected Uses:/p' | sed '1d;$d' | tr -d '[:space:]')
    test -z "$trusted" || exit 1
    for usage in 'TLS Web Server Authentication' 'TLS Web Client Authentication' 'Code Signing' 'E-mail Protection' 'Time Stamping' 'IPSec End System' 'IPSec Tunnel' 'IPSec User'; do
      echo "$trust" | sed -n '/^Rejected Uses:/,$p' | grep -Fq "$usage" || exit 1
    done
  fi
done
