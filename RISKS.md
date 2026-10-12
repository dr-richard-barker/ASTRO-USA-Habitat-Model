# Risks

| Risk | Effect | Mitigation | Owner |
|---|---|---|---|
| Design belongs to a 24-author team | Publishing without consent | Paper PDF/slides never committed; first push gated on recorded consent | R. Barker |
| Placeholder payloads read as real hardware | Misleading results | Payloads are generic, unbranded envelopes declared as assumptions; VR allow-list gate with a planted canary rejects any mesh not in the registry | R. Barker |
| Unknown HVAC, lights, insulation | CFD answers depend on placeholders | Every placeholder is a declared assumption with `ask_team`; results stamped with the ledger digest; S5 sensitivity screen | Team inputs |
| Fabricated or unverifiable numbers | Credibility | Ledger refuses unsourced values; every CFD number from committed solver output; citations verified before use | Claude |
| Silent geometry/solver errors | Wrong but "valid" results | Reload-and-measure checks, overlay gate, balance/age-identity gates, negative tests | Claude |
| Shared compute (another session's OpenFOAM campaign) | Killed or slowed runs | Host lock + wait for foreign containers; coarse-first; resumable state | Claude |
