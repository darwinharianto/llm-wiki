---
title: '3GPP 45009-f00: Transmitter/Receiver Synchronisation'
slug: 3gpp-45009-f00-transmitterreceiver-synchronisation
category: concepts
aliases: []
tags:
- shall
- information
- mobile
- requests
- codec
- frames
- phase
- mode
- sent
- channel
- downlink
- reallocation
- 3gpp
- synchronisation
sources:
- 2026-11-14-telequad-w01-16.md
- 2026-11-14-telequad-w02-16.md
- 2026-11-14-telequad-w03-16.md
- 2026-11-14-telequad-w04-16.md
- 2026-11-14-telequad-w05-16.md
- 2026-11-14-telequad-w06-16.md
- 2026-11-14-telequad-w07-16.md
- 2026-11-14-telequad-w08-16.md
- 2026-11-14-telequad-w09-16.md
- 2026-11-14-telequad-w10-16.md
created_at: '2026-11-14T05:19:09Z'
updated_at: '2026-11-14T05:20:20Z'
revision_count: 10
confidence: high
summary: "3.2.1.3\tTransmitter/Receiver Synchronisation The alternating transmission\
  \ of the codec mode information requires synchronisation of transmitting and receiving\
  \ ends, such that Co..."
---

# 3GPP 45009-f00: Transmitter/Receiver Synchronisation

3.2.1.3	Transmitter/Receiver Synchronisation The alternating transmission of the codec mode information requires synchronisation of transmitting and receiving ends, such that Codec Mode Indications and Codec Mode Commands/Requests are decoded in correct order. To ensure proper synchronisation, the codec mode information shall be transmitted aligned to the 26multiframe structure of the GSM system. The default transmission phase for TCH/AFS, TCH/WFS, and O-TCH/WFS shall be such that Codec Mode Indications are sent with speech frames having their first burst sent on TDMA frames according to table 3.2.1.3-1. The default transmission phase for TCH/AHS, O-TCH/AHS, and O-TCH/WHS shall be such that Codec Mode Indications are sent with speech frames having their first burst sent on TDMA frames according to table 3.2.1.3-2. For a mobile station indicating support for VAMOS, the default transmission phase for TCH/AFS and TCH/WFS shall be such that Codec Mode Indications are sent with speech frames having their first burst sent on TDMA frames according to table 3.2.1.3-3. For a mobile station indicating support for VAMOS, the default transmission phase for TCH/AHS shall be such that Codec Mode Indications are sent with speech frames having their first burst sent on TDMA frames according to table 3.2.1.3-4.

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-16.md]** (3GPP 45009-f00: Transmitter/Receiver Synchronisation: Extended Procedures & Parameters): This default phase of the Codec Mode Indication in downlink direction is called "odd", the alternative phase, one speech frame shifted, is called "even". The phase in uplink is always the same and is never changed. At call set-up, after a channel mode modify with consistent MultiRate configuration IE and after each reallocation of the circuit switched channel, the default phase (odd) shall be used in downlink direction. During a call, the phase of Codec Mode Indication may be changed in downlink by using a RATSCCH message. In case of reallocation failure and fall back to the channel before the reallocation attempt, the phase before the channel reallocation attempt shall be used again (except if a RATSCCH procedure is pending, see section 3.2.2.2 bullet 6).
