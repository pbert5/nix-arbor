FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac

ARG RUNNER_VERSION=2.338.0
ARG RUNNER_SHA256
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git jq libicu74 libssl3 libkrb5-3 rsync zlib1g \
      fonts-liberation libfontconfig1 libfreetype6 \
      libglib2.0-0t64 libnspr4 libnss3 libdbus-1-3 \
      libatk1.0-0t64 libatk-bridge2.0-0t64 libatspi2.0-0t64 \
      libcups2t64 libdrm2 libxcb1 libxkbcommon0 libx11-6 \
      libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
      libgbm1 libcairo2 libpango-1.0-0 libasound2t64 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1001 runner \
 && mkdir -p /opt/actions-runner /runner \
 && curl --fail --location --silent --show-error "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" -o /tmp/runner.tar.gz \
 && echo "${RUNNER_SHA256}  /tmp/runner.tar.gz" | sha256sum --check --status \
 && tar -xzf /tmp/runner.tar.gz -C /opt/actions-runner \
 && rm /tmp/runner.tar.gz \
 && /opt/actions-runner/bin/installdependencies.sh \
 && chown -R runner:runner /opt/actions-runner /runner
COPY --chmod=755 entrypoint.sh /usr/local/bin/runner-entrypoint
USER runner
WORKDIR /opt/actions-runner
ENTRYPOINT ["/usr/local/bin/runner-entrypoint"]
