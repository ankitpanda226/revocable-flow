# Human-managed campaign checkpoints

These small records are intended for normal owner-reviewed Git commits, never
runtime writes from GitHub Actions. Raw experiment artifacts stay outside Git.

`completed/after_post_001_013.json` authenticates the verified source chain. Its
two-copy archival attestation is currently **false**. Do not mark it true until
you have retained the original ZIP in two independent owner-controlled locations,
read both copies back and checked their SHA-256. Then record non-sensitive archive
references; do not put credentials or private filesystem/account details here.
Changes to archival bookkeeping do not modify the original scientific records.

`authorizations/post_update_014_023.json` deliberately does not exist yet. After
separate publication/live approval, the one authorized executor prints a template
with its exact run/job/execution commit and fresh invocation nonce. While that
same invocation waits, the owner creates this file once, using the template,
current Unix approval time and freshly reviewed tier/key/quota/spend values.
The owner commits only this small record using ordinary Git credentials. There
is no runtime write token, App, privileged branch or Administration permission.

Never edit, delete, move, replace or reuse an authorization to give a different
run or nonce permission. A restart obtains a fresh nonce and must stop. Do not
force-rewrite authorization/checkpoint history. If a run is interrupted or its
artifact is missing, quarantine the whole reserved scope and reconcile evidence
offline. Do not infer that unobserved requests were unattempted. Unknown requests
are not counted as confirmed calls or assigned privacy scores.

After every completed batch, download the sealed artifact immediately, validate
its complete predecessor chain/ledger, preserve the ZIP unchanged, and verify two
independent archival copies. Generate a small receipt with ZIP SHA-256, scientific
file-tree hash, cumulative ledger hash, run/authorization references and identities.
Verify copies before recording the attestation as true and committing a new
checkpoint summary. Hashes without the corresponding retained raw bytes are not
an archive. Keep prior receipts append-only. Never commit raw files, credentials,
generated caches or whole experiment ZIPs to the project repository.
