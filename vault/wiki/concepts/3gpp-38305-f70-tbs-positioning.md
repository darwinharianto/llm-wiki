---
title: '3GPP 38305-f70: TBS positioning'
slug: 3gpp-38305-f70-tbs-positioning
category: concepts
aliases: []
tags:
- data
- location
- rag
- information
- positioning
- assistance
- 3gpp
- transferred
- mode
- procedure
- initiated
- transfer
- based
- measurements
- '38305'
sources:
- 2026-11-14-telequad-w01-10.md
- 2026-11-14-telequad-w02-10.md
- 2026-11-14-telequad-w03-10.md
- 2026-11-14-telequad-w04-10.md
- 2026-11-14-telequad-w05-10.md
- 2026-11-14-telequad-w06-10.md
- 2026-11-14-telequad-w07-10.md
- 2026-11-14-telequad-w08-10.md
- 2026-11-14-telequad-w09-10.md
- 2026-11-14-telequad-w10-10.md
created_at: '2026-11-14T05:19:07Z'
updated_at: '2026-11-14T05:20:18Z'
revision_count: 10
confidence: high
summary: "8.7\tTBS positioning 8.7.1\tGeneral Terrestrial Beacon Systems (TBS) is\
  \ the standard generic term for a network of ground-based transmitters broadcasting\
  \ signals for geo-spatial p..."
---

# 3GPP 38305-f70: TBS positioning

8.7	TBS positioning 8.7.1	General Terrestrial Beacon Systems (TBS) is the standard generic term for a network of ground-based transmitters broadcasting signals for geo-spatial positioning with wide-area or regional coverage. The following TBSs are supported in this version of the specification: Three positioning modes are supported: 8.7.2	Information to be transferred between NG-RAN/5GC Elements This clause defines the information that may be transferred between LMF and UE. 8.7.2.1	Information that may be transferred from the LMF to UE Table 8.7.2.1-1 lists assistance data for both UE-assisted and UE-based modes that may be sent from the LMF to the UE. 8.7.2.1.1	Acquisition Assistance Acquisition assistance provides the MBS receiver with information about visible beacons, PN Codes, and other information of the MBS signals to enable a fast acquisition of the MBS signals. 8.7.2.1.2	Almanac Almanac assistance provides the MBS receiver with MBS beacon parameters that can be used to determine the UE position. 8.7.2.2	Information that may be transferred from the UE to LMF The information that may be signalled from the UE to the LMF is summarized in Table 8.7.2.2-1. 8.7.2.2.1	Standalone mode In Standalone mode, the UE reports the latitude, longitude and possibly altitude, together with an estimate of the location uncertainty, if available. The UE should also report an indication that TBS method is used and possibly other positioning methods used to calculate the fix. 8.7.2.2.2	UE-assisted mode In UE-assisted mode, the UE reports the TBS associated measurements, together with associated quality estimates.

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-10.md]** (3GPP 38305-f70: TBS positioning: Extended Procedures & Parameters): 8.7.2.2.3	UE-based mode In UE-based mode, the UE reports the latitude and longitude, together with an estimate of the location uncertainty, if available. 8.7.3	TBS Positioning Procedures 8.7.3.1	Capability Transfer Procedure The Capability Transfer procedure for TBS positioning is described in clause 7.1.2.1. 8.7.3.2	Assistance Data Transfer Procedure The purpose of this procedure is to enable the LMF to provide assistance data to the UE (e.g., as part of a positioning procedure) and the UE to request assistance data from the LMF (e.g., as part of a positioning procedure). 8.7.3.2.1	LMF initiated Assistance Data Delivery Figure 8.7.3.2.1-1 shows the Assistance Data Delivery operations for the network-assisted TBS method when the procedure is initiated by the LMF. 8.7.3.2.2	UE initiated Assistance Data Transfer Figure 8.7.3.2.2-1 shows the Assistance Data Transfer operations for the network-assisted TBS method when the procedure is initiated by the UE. 8.7.3.3	Location Information Transfer Procedure The purpose of this procedure is to enable the LMF to request position measurements or location estimate from the UE, or to enable the UE to provide location measurements to the LMF for position calculation. 8.7.3.3.1	LMF initiated Location Information Transfer Procedure Figure 8.7.3.3.1-1 shows the Location Information Transfer operations for the TBS method when the procedure is initiated by the LMF. 8.7.3.3.2	UE-initiated Location Information Delivery Procedure Figure 8.7.3.3.2-1 shows the Location Information delivery operations for the TBS method when the procedure is initiated by the UE.
