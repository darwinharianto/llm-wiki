---
title: '3GPP 25211-f00: Dedicated downlink physical channels'
slug: 3gpp-25211-f00-dedicated-downlink-physical-channels
category: concepts
aliases: []
tags:
- each
- data
- power
- service
- downlink
- dedicated
- 3gpp
- dpch
- channel
- frames
- slot
- tfci
- case
- mode
- dpchs
- pilot
- transmitted
- bits
- physical
- spreading
- compressed
sources:
- 2026-11-14-telequad-w01-09.md
- 2026-11-14-telequad-w02-09.md
- 2026-11-14-telequad-w03-09.md
- 2026-11-14-telequad-w04-09.md
- 2026-11-14-telequad-w05-09.md
- 2026-11-14-telequad-w06-09.md
- 2026-11-14-telequad-w07-09.md
- 2026-11-14-telequad-w08-09.md
- 2026-11-14-telequad-w09-09.md
- 2026-11-14-telequad-w10-09.md
created_at: '2026-11-14T05:19:07Z'
updated_at: '2026-11-14T05:20:17Z'
revision_count: 12
confidence: high
summary: "5.3.2\tDedicated downlink physical channels There are five types of downlink\
  \ dedicated physical channels, the Downlink Dedicated Physical Channel (downlink\
  \ DPCH), the Fractional ..."
---

# 3GPP 25211-f00: Dedicated downlink physical channels

5.3.2	Dedicated downlink physical channels There are five types of downlink dedicated physical channels, the Downlink Dedicated Physical Channel (downlink DPCH), the Fractional Dedicated Physical Channel (F-DPCH), the E-DCH Relative Grant Channel (E-RGCH), the E-DCH Hybrid ARQ Indicator Channel (E-HICH), and the Fractional Transmitted Precoding Indicator Channel (F-TPICH). The F-DPCH is described in subclause 5.3.2.6. Within one downlink DPCH, dedicated data generated at Layer 2 and above, i.e. the dedicated transport channel (DCH), is transmitted in time-multiplex with control information generated at Layer 1 (known pilot bits, TPC commands, and an optional TFCI). The downlink DPCH can thus be seen as a time multiplex of a downlink DPDCH and a downlink DPCCH, compare subclause 5.2.1. Figure 9 shows the frame structure of the downlink DPCH. Each frame of length 10 ms is split into 15 slots, each of length Tslot = 2560 chips, corresponding to one power-control period. The parameter k in figure 9 determines the total number of bits per downlink DPCH slot. It is related to the spreading factor SF of the physical channel as SF = 512/2k. The spreading factor may thus range from 512 down to 4. The exact number of bits of the different downlink DPCH fields (Npilot, NTPC, NTFCI, Ndata1 and Ndata2) is given in table 11. What slot format to use is configured by higher layers and can also be reconfigured by higher layers. There are basically two types of downlink Dedicated Physical Channels; those that include TFCI (e.g. for several simultaneous services) and those that do not include TFCI (e.g. for fixed-rate services). These types are reflected by the duplicated rows of table 11. It is the UTRAN that determines if a TFCI should be transmitted and it is mandatory for all UEs to support the use of TFCI in the downlink. The mapping of TFCI bits onto slots is described in [3]. In compressed frames, a different slot format is used compared to normal mode. There are two possible compressed slot formats that are labelled A and B. Slot format B shall be used in frames compressed by spreading factor reduction and slot format A shall be used in frames compressed by higher layer scheduling.

## Related Concepts

- Related trail: [[lte-ue-category|LTE ue-Category]] — Category information is used to allow the eNB to communicate effectively with all the UEs connected to it. The ue-Category defines a combined uplink and downlink capability as s...
- Related trail: [[iot-lora|IoT: LoRa]] — LoRa is a kind of LPWAN (Low Power Wide Area Network). I am not sure exactly where the word LoRa came from.. but many say "the name LoRa came from Long range low power Radio Net...

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-09.md]** (3GPP 25211-f00: Dedicated downlink physical channels: Extended Procedures & Parameters): The channel bit and symbol rates given in table 11 are the rates immediately before spreading. The pilot bit patterns are described in table 12. The shadowed column part of pilot bit pattern is defined as FSW and FSWs can be used to confirm frame synchronization. (The value of the pilot bit pattern other than FSWs shall be "11".) In table 12, the transmission order is from left to right. Symbol repetition is used to fill up the fields. Denote the bits in one of these fields in normal mode by x1, x2, x3, …, xX. In compressed mode the following bit sequence is sent in corresponding field: x1, x2, x1, x2, x3, x4, x3, x4,…, xX,. The relationship between the TPC symbol and the transmitter power control command is presented in table 13. Multicode transmission may be employed in the downlink, i.e. the CCTrCH (see [3]) is mapped onto several parallel downlink DPCHs using the same spreading factor. DTX bits are transmitted during the corresponding time period for the additional downlink DPCHs, see figure 10. In case there are several CCTrCHs mapped to different DPCHs transmitted to the same UE different spreading factors can be used on DPCHs to which different CCTrCHs are mapped. Also in this case, Layer 1 control information is only transmitted on the first DPCH while DTX bits are transmitted during the corresponding time period for the additional DPCHs.
