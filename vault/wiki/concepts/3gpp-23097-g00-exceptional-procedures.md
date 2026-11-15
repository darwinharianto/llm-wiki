---
title: '3GPP 23097-g00: Exceptional Procedures'
slug: 3gpp-23097-g00-exceptional-procedures
category: concepts
aliases: []
tags:
- network
- data
- subscriber
- 3gpp
- phase
- call
- camel
- profile
- indication
- barrings
- calls
- supporting
sources:
- 2026-11-14-telequad-w01-19.md
- 2026-11-14-telequad-w02-19.md
- 2026-11-14-telequad-w03-19.md
- 2026-11-14-telequad-w04-19.md
- 2026-11-14-telequad-w05-19.md
- 2026-11-14-telequad-w06-19.md
- 2026-11-14-telequad-w07-19.md
- 2026-11-14-telequad-w08-19.md
- 2026-11-14-telequad-w09-19.md
- 2026-11-14-telequad-w10-19.md
created_at: '2026-11-14T05:19:10Z'
updated_at: '2026-11-14T05:20:22Z'
revision_count: 10
confidence: high
summary: "7.12\tExceptional Procedures 7.12.1\tRoaming into a network not supporting\
  \ CAMEL Phase 3 When roaming into a network not supporting CAMEL Phase 3, only the\
  \ functionality of MSP Ph..."
---

# 3GPP 23097-g00: Exceptional Procedures

7.12	Exceptional Procedures 7.12.1	Roaming into a network not supporting CAMEL Phase 3 When roaming into a network not supporting CAMEL Phase 3, only the functionality of MSP Phase 1 will be available to an MSP subscriber. The default profile subscription information shall apply to all supplementary services, excluding Call Forwarding and Call Barring, provisioned per profile. 7.12.2	Roaming into a network not supporting CAMEL Phase 2 This subclause details MSP specific handling for roaming into a network not supporting CAMEL Phase 2. Other handling for this scenario is described in 3G TS 23.078. 7.12.2.1	Actions required on Location Update The HLR will send the outgoing call barring data and outgoing ODB data, specific to the default profile, to the VLR. 7.12.2.2	MO call handling When an MSP subscriber roams into a network not supporting CAMEL Phase 2, the default profile will be used for all outgoing traffic. 7.12.2.3	MT call handling

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-19.md]** (3GPP 23097-g00: Exceptional Procedures: Extended Procedures & Parameters): MT calls to any profile will be received by the subscriber (subject to call forwardings and call barrings provided in the gsmSCF on the called profile), although no indication of the called profile will be received. The HLR will not allow OR, this means that for MT calls, the GMSC will always support CAMEL Phase 2, allowing the gsmSCF to invoke appropriate Call Forwardings and Call Barrings. 7.12.2.4	MO short message handling MO short messages will be sent from and charged to the default profile. 7.12.3	Lack of availability of the Network Indication of Alerting feature If an MSP subscriber roams into a network not supporting the Network Indication of Alerting feature, or is using an MS that does not support the Network indication of Alerting feature, then the subscriber will still receive all MT calls, but no indication of the called profile will be given. Annex A (informative): Provision and Withdrawal of MSP

## Contradictions & Tensions

- **[2026-11-14 | 2026-11-14-telequad-w04-19.md]** Potential tension/nuance noted: MT calls to any profile will be received by the subscriber (subject to call forwardings and call barrings provided in the gsmSCF on the called profile), although no indication of the called profile will be received. The HLR will not allow OR, this means that for MT calls, the GMSC will always support CAMEL Phase 2, allowing the gsmSCF to invoke appropriate Call Forwardings and Call Barrings. 7.12.2.4	MO short message handling MO short messages will be sent from and charged to the default profile. 7.12.3	Lack of availability of the Network Indication of Alerting feature If an MSP subscriber roams into a network not supporting the Network Indication of Alerting feature, or is using an MS that does not support the Network indication of Alerting feature, then the subscriber will still receive all MT calls, but no indication of the called profile will be given. Annex A (informative): Provision and Withdrawal of MSP
