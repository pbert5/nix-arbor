# Enroll a portable Arbor identity

The Windows or Linux client creates and keeps a separate Ed25519 Arbor identity. It exchanges two public JSON files with an operator who controls a trusted Registry authority. Enrollment does not change the Yggdrasil peer configuration or open any service ports.

Install Python 3.13+ on Windows or Python 3.10+ on Linux. In the Python environment used by Arbor Connect, run `python -m pip install PyNaCl`. Use a state directory under your private user profile on a local filesystem. On Windows, that filesystem must support ACLs and Windows PowerShell must be available. Keep the enrollment directory private when backing it up. It contains your signing key.

1. Obtain the authority ID and its full Ed25519 public key from an authenticated operator. The key uses unpadded base64url as in the Registry bootstrap authority file. On the joining computer, substitute your own values and run this command from the tool directory.

   ```sh
   python arbor_enrollment.py request --state-dir ./my-arbor --node guest1 --authority parent1 --authority-key PUBLIC_KEY --out request.json
   ```

2. Transfer `request.json` to the operator. Independently compare the entire printed SHA-256 digest, node ID, platform, and authority ID. An unapproved request lasts 15 minutes. Repeating the command with a fresh output filename returns the same request while valid or creates a new one using the same key after expiry.

3. On an authority host with Registry enrollment operations installed, the authorized operator can use its local adapter. This example uses a POSIX shell and jq. Replace the two example variables after independently confirming the request. The daemon must trust the authority through its configured bootstrap public key and have its matching signer in its protected key directory. Access to its authenticated Unix socket and token is required.

   ```sh
   authority=parent1
   confirmed_digest=REPLACE_WITH_INDEPENDENTLY_CONFIRMED_DIGEST
   jq -n --slurpfile req request.json --arg id "$authority" --arg digest "$confirmed_digest" \
     '{protocol:"arbor-manager/runtime-adapter",version:1,operation:"enrollment/approve",
       data:{authorityId:$id,request:$req[0],requestDigest:$digest}}' > approve-input.json
   arbor-registry-manager-adapter < approve-input.json > approve-response.json &&
     jq -e 'select(.status == "accepted") | .approval | select(.schema == "node-identity")' \
       approve-response.json > approval.json
   ```

   The root Registry pin `6147dd3` provides the Python signing primitive `approve_enrollment` and authenticated daemon `ingest` operation. Its Manager adapter only exposes local bootstrap and summary operations. The command above requires the enrollment-capable adapter and daemon from Registry commit `0b149d5` or a compatible release. On an installation using the older pin, an existing administrator-controlled enrollment workflow must verify the request digest, identity and expiry, sign it with the configured authority, ingest the signed identity and confirm acceptance. Without an approving workflow the request stays pending.

4. Return only the signed `approval.json` to the joining computer. Verify it against the originally pinned authority and the locally held signing key.

   ```sh
   python arbor_enrollment.py finish --state-dir ./my-arbor --approval approval.json
   python arbor_enrollment.py status --state-dir ./my-arbor
   ```

   Local status records verification of the signed identity. The operator can inspect Registry on the approving host for acceptance and current lifecycle state. A previously issued approval may be finished after the request expires. The portable client runs without a local Registry daemon and does not replicate Registry or monitor later revocations.

For tests, run `python test_arbor_enrollment.py -v` in this directory. With the pinned Registry runtime available on Linux through `PYTHONPATH`, the test also signs with its real authority helper and checks actual runtime acceptance using temporary identities and a file provider.
