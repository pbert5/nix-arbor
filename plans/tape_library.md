we should integrate for managing the content in the tape library: a great breakdown: Yes. Git-annex is almost exactly the right **upper layer** for this, but it should not be the whole tape-library manager.

The split should be:

```text
git-annex:
  knows what files exist
  knows their content hashes
  knows which remotes claim to have them
  enforces numcopies
  verifies content with fsck
  requests store / retrieve / remove

LTFS tape library manager:
  knows tape barcodes
  knows drive state
  knows changer state
  mounts and unmounts LTFS
  queues jobs
  prevents interruption
  maps annex keys to physical tapes
```

That is a very clean separation.

## Why git-annex fits so well

Git-annex is built for managing large files without putting the file contents directly into Git. Its docs describe it as managing files with Git while storing the file contents separately, which is exactly what you want for tape, object stores, SeaweedFS, archive disks, and compute-node caches. ([git-annex][1])

The magic is that git-annex already gives you:

* **Content identity**

  * A file is not just “`sample1.tif`”
  * It is an annex key based on size, hash, and backend
  * So renames do not confuse the archive

* **Location tracking**

  * Git-annex can know that a file exists on `hot-seaweed`, `storage-node`, `tape-library`, etc.

* **Copy policy**

  * `numcopies` lets you say “do not consider this safe unless there are at least N copies”

* **Verification**

  * `git annex fsck` checks annexed files for consistency and can warn about or fix problems. ([git-annex][2])

* **Pull-on-demand**

  * Your workstation can have tiny pointer files, then fetch the actual data when needed

That is basically the perfect model for your “I want to know what tape has this file and fetch it when needed” goal.

## The best integration: a custom git-annex special remote

Git-annex supports special remotes, including external special remotes. The external remote docs say you can implement a new remote by writing a program named like `git-annex-remote-$name`, installing it in `PATH`, and initializing it with `git annex initremote ... type=external externaltype=$name`. ([git-annex][3])

So your tape manager could literally become:

```bash
git annex initremote tape-library type=external externaltype=ltfs-library encryption=none
```

Then git-annex asks the remote things like:

```text
Can you store this key?
Can you retrieve this key?
Do you have this key?
Remove this key?
```

Your LTFS manager handles the physical reality:

```text
Need key SHA256E-s1234--abcd.tif
  check catalog
  key is on tape B00017
  reserve changer
  load B00017 into drive 1
  mount LTFS read-only
  copy object out
  verify hash
  return success to git-annex
```

That is exactly the kind of backend git-annex special remotes are meant for.

## The tape part should not pretend to be normal disk

LTFS makes tape look like a filesystem, but tape is still sequential. LTFS-formatted tape can be accessed like files and directories, but modifications and deletes do not behave like a normal disk because old tape blocks are not reclaimed unless the tape is reformatted. ([Wikipedia][4])

So the tape manager should avoid random “filesystem-like” behavior.

Better pattern:

```text
Append objects to tape
Never modify old objects
Never rename objects after writing
Never trust a write until verified
Only tell git-annex "STORE-SUCCESS" after full write + sync + verify
```

That fits git-annex object storage really well, because annex objects are immutable. A content hash object should never need to change. If the file changes, it becomes a new annex key.

## Two possible designs

### Design A: one git-annex special remote per tape

Example:

```text
tape-B00001
tape-B00002
tape-B00003
```

Pros:

* Very easy mental model
* `git annex whereis file` can show the exact tape remote
* Each tape is self-contained
* Good for manual recovery

Cons:

* Many remotes
* More annoying automation
* Harder to schedule across a real library
* Git-annex metadata could get noisy

This is viable, and other people have explored tape-per-remote style designs. There is even a git-annex forum thread from someone working on a tape-media special remote where each cartridge is tracked as a dedicated special remote in a `tape` group. ([git-annex][5])

### Design B: one special remote for the whole tape library

Example:

```text
remote name:
  tape-library

internal catalog:
  key -> barcode -> path -> offset-ish metadata -> verification status
```

Pros:

* Cleaner user experience
* One remote in git-annex
* Your software handles scheduling, queueing, loading, drive contention, and anti-interruption
* Better match for TL2000 with two drives and one changer

Cons:

* `git annex whereis` may only say “tape-library” unless your remote exposes extra location info
* You need your own catalog database
* More custom code

For your TL2000, this is probably the better architecture.

## How I would store each tape

Each LTFS tape should be independently understandable.

Something like:

```text
/
  README.txt
  TAPE-MANIFEST.json
  TAPE-MANIFEST.json.sha256
  annex-objects/
    SHA256E-s123--abc...dat
    SHA256E-s456--def...tif
  indexes/
    manifest-000001.jsonl
    manifest-000001.jsonl.sha256
  recovery/
    repo.bundle
    repo.bundle.sha256
```

Important detail: the canonical copy should be the **annex object**, not just the pretty filename.

Then the manifest maps:

```json
{
  "annex_key": "SHA256E-s123456--abcdef.tif",
  "original_paths": ["datasets/pigskin/day1/sample_A.tif"],
  "size": 123456,
  "sha256": "abcdef...",
  "written_at": "2026-04-28T...",
  "tape_barcode": "B00017",
  "ltfs_path": "/annex-objects/SHA256E-s123456--abcdef.tif"
}
```

That means even without your software, future-you can mount the tape, read the manifest, and recover the objects.

## Should you use `exporttree=yes`?

Maybe, but I would not use it as the primary archive format.

Git-annex has an `export` mode that can export a tree to a special remote using normal filenames instead of key-named annex objects. The docs say normal special remotes store objects by key, which is reliable but obscures filenames, while exporting replicates the tree “as-is.” ([git-annex][6])

That is nice for a human-browsable tape:

```text
/tape-root/
  project-a/
    image1.tif
    image2.tif
```

But for a durable tape archive, key-named immutable objects are safer:

```text
/tape-root/
  annex-objects/
    SHA256E-s...
```

I would do both only if you really care about browseability:

```text
Primary:
  annex object store

Optional:
  exported human-readable snapshot
```

For serious archival, I would prioritize the annex object store plus a manifest.

## Where git-annex stops

Git-annex will not solve these tape-specific problems by itself:

```text
Which drive is free?
Can I interrupt this mount?
Is the changer busy?
What if drive 1 is reading and drive 2 is writing?
What if the LTFS mount hangs?
What if a tape is full?
What if a write partially completed?
What if power dies during index update?
Which tape should receive the next object?
```

That is your tape-library manager’s job.

The manager needs:

```text
global library lock
per-drive lock
per-tape lock
job queue
mount state machine
write staging area
post-write verification
catalog transaction log
resume/recovery mode
```

Git-annex should only see a clean remote that either succeeds or fails.

## The architecture I’d build

```text
User / compute node
  runs git annex get/copy/sync

Git-annex
  tracks keys, filenames, history, locations, numcopies

git-annex-remote-ltfs-library
  external special remote adapter

Tape library service
  REST/socket API
  queue
  scheduler
  drive/changer locking
  catalog DB

LTFS layer
  mount/unmount tapes
  write/read immutable annex objects

TL2000 hardware
  changer + two LTO-5 drives
```

In command form, the user experience should eventually look like:

```bash
git annex copy results/ --to tape-library
git annex get raw/day1/sample_A.tif --from tape-library
git annex whereis raw/day1/sample_A.tif
git annex fsck --from tape-library
```

## My actual recommendation

Use git-annex as the **truth layer for content identity and copy policy**.

Use your custom LTFS software as the **physical archive backend**.

Do not try to make LTFS itself behave like a general shared filesystem for active work. Treat LTFS tapes as immutable-ish cartridges full of annex objects plus manifests.

Best final model:

```text
Radicle/Git:
  repo history and annex metadata

SeaweedFS:
  hot active cache

git-annex:
  content-addressed data control plane

LTFS library manager:
  robotic cold storage backend

Each tape:
  self-describing recovery unit
```

So yes, your instinct is right. Git-annex is not just compatible with an LTFS library manager, it is probably one of the best existing foundations for building one. The only missing piece is the custom special remote that knows how to talk to your TL2000 queue, mount tapes, and maintain a physical object catalog.

[1]: https://git-annex.branchable.com/git-annex/?utm_source=chatgpt.com "git-annex man page - Branchable"
[2]: https://git-annex.branchable.com/git-annex-fsck/?utm_source=chatgpt.com "git-annex-fsck"
[3]: https://git-annex.branchable.com/special_remotes/external/?utm_source=chatgpt.com "external - git-annex - Branchable"
[4]: https://en.wikipedia.org/wiki/Linear_Tape_File_System?utm_source=chatgpt.com "Linear Tape File System"
[5]: https://git-annex.branchable.com/forum/Fill_remotes_sequentially/?utm_source=chatgpt.com "Fill remotes sequentially - git-annex - Branchable"
[6]: https://git-annex.branchable.com/git-annex-export/?utm_source=chatgpt.com "git-annex-export - Branchable"
