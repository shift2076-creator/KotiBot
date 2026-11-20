# Matter PAA root certificates

The CSA production device-attestation roots (DER files), copied unchanged from
`credentials/production/paa-root-certs` in https://github.com/project-chip/connectedhomeip
at commit `1a9d06f` (Apache-2.0). chip-tool uses them via `--paa-trust-store-path`
so production devices such as the Tapo H110 pass attestation. To refresh, copy the
`.der` files from a newer commit and update this line.
