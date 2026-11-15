---
title: '3GPP 25996-f00: Spatial parameters for the MS'
slug: 3gpp-25996-f00-spatial-parameters-for-the-ms
category: concepts
aliases: []
tags:
- each
- path
- power
- angle
- antenna
- mobile
- direction
- travel
- 3gpp
- laplacian
- parameters
- distribution
sources:
- 2026-11-14-telequad-w01-05.md
- 2026-11-14-telequad-w02-05.md
- 2026-11-14-telequad-w03-05.md
- 2026-11-14-telequad-w04-05.md
- 2026-11-14-telequad-w05-05.md
- 2026-11-14-telequad-w06-05.md
- 2026-11-14-telequad-w07-05.md
- 2026-11-14-telequad-w08-05.md
- 2026-11-14-telequad-w09-05.md
- 2026-11-14-telequad-w10-05.md
created_at: '2026-11-14T05:19:06Z'
updated_at: '2026-11-14T05:20:15Z'
revision_count: 11
confidence: high
summary: "4.6\tSpatial parameters for the MS 4.6.1\tMS antenna pattern For each and\
  \ every antenna element at the MS, the antenna pattern will be assumed omni directional\
  \ with an antenna gai..."
---

# 3GPP 25996-f00: Spatial parameters for the MS

4.6	Spatial parameters for the MS 4.6.1	MS antenna pattern For each and every antenna element at the MS, the antenna pattern will be assumed omni directional with an antenna gain of -1 dBi. 4.6.2	Per-path MS angle spread (AS) The MS per-path AS is defined as the root mean square (RMS) of angles of an incident path's power at the MS array. Two values of the path's angle spread are considered: 4.6.3	Per-path MS angle of arrival The per-path Angle of Arrival (AoA) is defined as the mean of angles of an incident path's power at the UE/Mobile Station array with respect to the broadside as shown Figure 4.5. Three different per-path AoA values at the MS are suggested for the cases of a non-uniform PAS, see Table 4.1 for details: 4.6.4	Per-path MS power azimuth spectrum The Laplacian distribution and the Uniform distribution are used to model the per-path Power Azimuth Spectrum (PAS) at the MS. The Power Azimuth Spectrum (PAS) of a path arriving at the MS is modeled as either a Laplacian distribution or a uniform over 360 degree distribution.

## Related Concepts

- Related trail: [[3gpp-25211-f00-dedicated-downlink-physical-channels|3GPP 25211-f00: Dedicated downlink physical channels]] — 5.3.2	Dedicated downlink physical channels There are five types of downlink dedicated physical channels, the Downlink Dedicated Physical Channel (downlink DPCH), the Fractional ...

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-05.md]** (3GPP 25996-f00: Spatial parameters for the MS: Extended Procedures & Parameters): For an incoming AOA  and RMS angle-spread , the MS per-path Laplacian PAS value at an angle  is given by: where both angles and  are given with respect to the boresight of the antenna elements. It is assumed that all antenna elements' orientations are aligned. Also, P is the average received power and No is the normalization constant: In the above equation,  represents path components (sub-rays) of the path power arriving at an incoming AoA . The distribution of these path components is TBD. 4.6.5	MS direction of travel The mobile station direction of travel is defined with respect to the broadside of the mobile antenna array as shown in Figure 4.6. 4.6.6	Per-path Doppler spectrum The per-path Doppler spectrum is defined as a function of the direction of travel and the per-path PAS and AoA at the MS. This should correspond to the per-path fading behavior for either the correlation-based or ray-based method.
