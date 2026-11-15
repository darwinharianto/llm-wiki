---
title: '3GPP 21915-f00: Numerologies, waveform and frame structure'
slug: 3gpp-21915-f00-numerologies-waveform-and-frame-structure
category: concepts
aliases: []
tags:
- rag
- ofdm
- waveform
- domain
- each
- channel
- below
- slot
- cases
- downlink
- approximately
- case
- 3gpp
- cyclic
- frame
- shown
sources:
- 2026-11-14-telequad-w01-02.md
- 2026-11-14-telequad-w02-02.md
- 2026-11-14-telequad-w03-02.md
- 2026-11-14-telequad-w04-02.md
- 2026-11-14-telequad-w05-02.md
- 2026-11-14-telequad-w06-02.md
- 2026-11-14-telequad-w07-02.md
- 2026-11-14-telequad-w08-02.md
- 2026-11-14-telequad-w09-02.md
- 2026-11-14-telequad-w10-02.md
created_at: '2026-11-14T05:19:05Z'
updated_at: '2026-11-14T05:20:14Z'
revision_count: 11
confidence: high
summary: "5.5.4.1\tNumerologies, waveform and frame structure Similar to LTE, OFDM\
  \ with Cyclic Prefix (CP) is used as the downlink (DL) waveform for NR. In contrast\
  \ to LTE, OFDM can also b..."
---

# 3GPP 21915-f00: Numerologies, waveform and frame structure

5.5.4.1	Numerologies, waveform and frame structure Similar to LTE, OFDM with Cyclic Prefix (CP) is used as the downlink (DL) waveform for NR. In contrast to LTE, OFDM can also be used in the NR uplink (UL) direction. As a complement waveform with lower peak-to-average power ratio (PAPR) to improve UL coverage, DFT-s-OFDM (OFDM with Discrete Fourier Transform precoding) can be used in the uplink although limited to single-layer transmission only. To cope with various deployment scenarios, NR supports a wide range of carrier frequencies (within two possible ranges) and channel bandwidths, as shown in the table below. To allow for such a flexibility, NR uses a flexible frame structure, with different Subcarrier Spacings (SCS). The SCS is the distance between the centres of two consecutive subcarriers, and the possible values for SCS are (in kHz): 15; 30; 60; 120 and 240. This is referred to as "multiple numerologies". A consecutive series of 12 subcarriers forms one Resource Block (RB). An NR channel bandwidth consists of a number of RBs. A Resource Element (RE) is defined as a unit of one subcarrier (frequency domain) and one OFDM symbol (time domain). As for the time domain, it is divided in 10ms radio frames, each on consisting in 10 subframes of 1ms each, as shown in the picture below. In turn, each subframe consists of 1/2/4/8/16 slots -shown in different colors- depending on the selected SCS/numerology. The figure shows the cases of SCS values of 15; 30; 60 and 120 KHz, while the table below provides the full list of possible numerologies in NR.

## Related Concepts

- Related trail: [[3gpp-25996-f00-spatial-parameters-for-the-ms|3GPP 25996-f00: Spatial parameters for the MS]] — 4.6	Spatial parameters for the MS 4.6.1	MS antenna pattern For each and every antenna element at the MS, the antenna pattern will be assumed omni directional with an antenna gai...

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-02.md]** (3GPP 21915-f00: Numerologies, waveform and frame structure: Extended Procedures & Parameters): As shown in the figure for the 15 kHz case, each slot consists of 14 OFDM symbols (independently of the SCS) preceded by a cyclic prefix (CP). Note that, for the 60 kHz SCS, an extended CP is possible. The extended CP is approximately four times longer than the normal CP and is used for cells having large delay spread. In this case, one slot consists of only 12 OFDM symbols. The OFDM symbol duration and CP length are inversely proportional of the SCS. for 15 kHz SCS, the OFDM symbol duration is approximately 66.6 µs and the CP length is approximately 4.7 µs. When the SCS is doubled, i.e. 30 kHz, the OFDM and CP lengths are approximately devided by two compared to the 15kHz SCS. NR supports both FDD and TDD operation with the same frame structure. In the case of TDD, and as to allow for flexible traffic adaptation, each OFDM symbol in a slot can be classified as 'downlink', 'uplink' or 'flexible' (i.e. either downlink or uplink). This can be configured semi-statically or it can change dynamically as part of the scheduling decision. Transmissions are usually carried out over one slot. In specific cases, transmissions can be carried out over only a fraction of a slot, with the minimum set to only two symbols. Such very short transmissions mainly target usage cases requiring low latency, such as some URLLC (Ultra Reliable, Low Latency) services.
