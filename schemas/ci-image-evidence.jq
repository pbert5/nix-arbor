{
  schemaVersion: 1,
  repository: $repository,
  image: $image,
  source: {commit: $sourceSha, tree: $sourceTree, manifestSha256: $manifestSha256},
  build: {
    context: $context,
    dockerfile: $dockerfile,
    dockerfileSha256: $dockerfileSha256,
    platforms: ($platforms | split(","))
  },
  cache: $cache,
  artifact: {
    pushTag: $reference,
    digest: $digest,
    immutableReference: ($pullReference + "@" + $digest)
  }
}
