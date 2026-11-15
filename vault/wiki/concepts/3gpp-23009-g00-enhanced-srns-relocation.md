---
title: '3GPP 23009-g00: Enhanced SRNS Relocation'
slug: 3gpp-23009-g00-enhanced-srns-relocation
category: concepts
aliases: []
tags:
- location
- enhanced
- relocation
- message
- shall
- 3gpp
- necessary
- complete
- srns
sources:
- 2026-11-14-telequad-w01-01.md
- 2026-11-14-telequad-w02-01.md
- 2026-11-14-telequad-w03-01.md
- 2026-11-14-telequad-w04-01.md
- 2026-11-14-telequad-w05-01.md
- 2026-11-14-telequad-w06-01.md
- 2026-11-14-telequad-w07-01.md
- 2026-11-14-telequad-w08-01.md
- 2026-11-14-telequad-w09-01.md
- 2026-11-14-telequad-w10-01.md
created_at: '2026-11-14T05:19:05Z'
updated_at: '2026-11-14T05:20:13Z'
revision_count: 12
confidence: high
summary: "6.2.3.1.2\tEnhanced SRNS Relocation The successful operation of the Enhanced\
  \ SRNS Relocation procedure is as follows. When the Serving RNS (RNS-A) makes the\
  \ decision to perform t..."
---

# 3GPP 23009-g00: Enhanced SRNS Relocation

6.2.3.1.2	Enhanced SRNS Relocation The successful operation of the Enhanced SRNS Relocation procedure is as follows. When the Serving RNS (RNS-A) makes the decision to perform the Enhanced SRNS Relocation procedure it will send an IUR-ENHANCED- RELOCATION-REQUEST message to the new RNS (RNSB). The IUR-ENHANCED RELOCATION-REQUEST message shall contain the necessary information to set up a CS Radio Access Bearer in RNS-B. When RNS-B receives the IUR-ENHANCED-RELOCATION-REQUEST message it shall take the necessary actions to establish the new Iu transport bearers for the Radio Access Bearer related to 3G_MSCA for the UE in question, as described in detail in the 3GPP TS 25.430 series and 3GPP TS 25.413, and the new transport bearers for the Radio Access Bearer related to RNS-A. to enable data forwarding. RNS-B shall initialize the Iu UP towards RNS A, if necessary. Once resource allocation has been completed by RNS-B it shall return an IUR-ENHANCED-RELOCATION-RESPONSE message to RNC-A. If the resources cannot be allocated, RNS-B returns an IUR-ENHANCED-RELOCATION-FAILURE message to RNS-A, and RNS-A terminates the procedure.

## Related Concepts

- Related trail: [[3gpp-32240-f50-charging-levels-and-correlation|3GPP 32240-f50: Charging levels and correlation]] — 5.3	Charging levels and correlation 5.3.1	Bearer level charging 5.3.1.1	Bearer charging based on bearer / tele- / supplementary service Charging data are also collected for supp...
- Related trail: [[3gpp-spec-23108-g00-03|3GPP Spec 23108-g00 (03)]] — 7.1	General Clause 7 contains examples of how the network may group together the elementary procedures (i.e. the procedures defined in clauses 3 to 5) in order to provide normal...

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-01.md]** (3GPP 23009-g00: Enhanced SRNS Relocation: Extended Procedures & Parameters): After transmission of the IUR-ENHANCED-RELOCATION-RESPONSE message RNS-B and RNS-A act as follows: After 3G_MSCA has received the IU-ENHANCED-RELOCATION-COMPLETE-REQUEST message from RNS-B, it shall start to configure the necessary Iu resources for the RNS-B and send the IU-ENHANCED-RELOCATION-COMPLETE-RESPONSE message to RNS-B. After RNC-B has received the IU-ENHANCED-RELOCATION-COMPLETE-RESPONSE message, it shall start to configure the Iu transport bearer for each Radio Access Bearer between the MSC-A and RNC-B and perform Iu UP initialization, if necessary. After the completion of the Iu UP initialization, RNS-B shall send an IU-ENHANCED-RELOCATION-COMPLETE-CONFIRM message to 3G_MSC-A. After 3G_MSC-A has received the IU-ENHANCED-RELOCATION-COMPLETE-CONFIRM message from RNS-B, it shall begin to release the resources associated to the RNS-A. In figures 11a and 11b, the resources are released by using the IURELEASECOMMAND sequence.
