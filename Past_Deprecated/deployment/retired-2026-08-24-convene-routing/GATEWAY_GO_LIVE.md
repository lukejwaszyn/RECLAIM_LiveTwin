# MacBook scenario-host go/no-go tracker

> The Windows 10 desktop owns live-data go-live. This tracker covers only the
> MacBook scenario host and does not authorize cRIO or direct-cloud access.

## Required gates

- [x] `mode` is `harness` or deliberate `replay`.
- [x] `9070` and `9080` bind only to `127.0.0.1`.
- [x] Direct transport is `console`; VM ingest token is absent.
- [x] Convene uses the MacBook-specific machine credential.
- [x] Scenario fields retain exact canonical names; `sim_` is forbidden.
- [x] Nominal, outage, and lunar component scenarios have passed.
- [x] Supplied Windows capture parses as 5,894 × 34 consistent records.
- [x] A bounded capture replay reached Convene with no failures or drops.

## Stop conditions

Stop the MacBook service if it binds a non-loopback interface, reports
`mode=live`, receives a VM ingest token, connects to the cRIO, emits `sim_`, or
publishes an unlabeled scenario source.

Windows live-gateway, cloud-engine, and Convene-to-VM acceptance remain separate
workstreams.
