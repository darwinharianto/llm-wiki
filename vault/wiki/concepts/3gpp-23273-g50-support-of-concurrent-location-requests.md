---
title: '3GPP 23273-g50: Support of Concurrent Location Requests'
slug: 3gpp-23273-g50-support-of-concurrent-location-requests
category: concepts
aliases: []
tags:
- requests
- location
- concurrent
- entity
- request
- combine
- support
sources:
- 2026-11-14-telequad-w01-00.md
- 2026-11-14-telequad-w02-00.md
- 2026-11-14-telequad-w03-00.md
- 2026-11-14-telequad-w04-00.md
- 2026-11-14-telequad-w05-00.md
- 2026-11-14-telequad-w06-00.md
- 2026-11-14-telequad-w07-00.md
- 2026-11-14-telequad-w08-00.md
- 2026-11-14-telequad-w09-00.md
- 2026-11-14-telequad-w10-00.md
created_at: '2026-11-14T05:19:05Z'
updated_at: '2026-11-14T05:20:13Z'
revision_count: 13
confidence: high
summary: "5.7\tSupport of Concurrent Location Requests 5.7.1\tGeneral Concurrent Location\
  \ Requests occur when any entity (e.g. UE, AMF, LMF, GMLC, NEF): In either case,\
  \ if allowed by the Qo..."
---

# 3GPP 23273-g50: Support of Concurrent Location Requests

5.7	Support of Concurrent Location Requests 5.7.1	General Concurrent Location Requests occur when any entity (e.g. UE, AMF, LMF, GMLC, NEF): In either case, if allowed by the QoS requirements and privacy settings, the entity may combine the concurrent location requests by fully executing one of the requests and using the ensuing location estimate result(s) to satisfy the other request(s) without fully executing the latter. When concurrent location requests are supported, each entity needs to ensure it correlates each location/position response with the associated request and different concurrent location requests shall be treated separately without any dependency on one another by any entity. If the entity, either itself or in association with another entity, cannot support concurrent location requests or it can only support up to a certain number of concurrent location requests, it can reject or defer a new concurrent request or cancel one or more existing requests. For Case B, it can also allow the new location request to proceed concurrently with and separately from the previous requests. LCS Client/AF priority and any other relevant priority information (e.g. UE subscription preferences) should be considered when rejecting or deferring a concurrent request or when cancelling one or more existing requests. In particular, location requests associated with emergency services or lawful interception clients should be given priority over other location requests. 5.7.2	Combining location requests by an H-GMLC or NEF An H-GMLC or NEF may combine concurrent location requests (e.g. 5GC-MT LR, 5GC-MO LR, 5GC-NI LR) for the same target UE by executing only one request and using the ensuing location estimate result(s) to satisfy the other request(s).

## Related Concepts

- Related trail: [[3gpp-23009-g00-enhanced-srns-relocation|3GPP 23009-g00: Enhanced SRNS Relocation]] — 6.2.3.1.2	Enhanced SRNS Relocation The successful operation of the Enhanced SRNS Relocation procedure is as follows. When the Serving RNS (RNS-A) makes the decision to perform t...
- Related trail: [[3gpp-23012-g00-overload-protection|3GPP 23012-g00: Overload Protection]] — 3.7	Overload Protection 3.7.1	Overview As the number of mobile devices increase and become more automated (Machine Type Communication, MTC type devices) the network is at greate...
- Related trail: [[3gpp-38305-f70-tbs-positioning|3GPP 38305-f70: TBS positioning]] — 8.7	TBS positioning 8.7.1	General Terrestrial Beacon Systems (TBS) is the standard generic term for a network of ground-based transmitters broadcasting signals for geo-spatial p...

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-00.md]** (3GPP 23273-g50: Support of Concurrent Location Requests: Extended Procedures & Parameters): The conditions for this are as follows: An H-GMLC may also combine concurrent location requests in the case of a bulk location request for a group of UEs as described in clause 6.8. 5.7.3	Combining location requests by a V-GMLC A V GMLC may combine concurrent 5GC-MT LR and 5GC-MO-LR related location requests for the same target UE provided it is clear and unambiguous for any 5GC-MT LR that will not be fully executed (e.g. from the contents of any location request received from the H GMLC) that no outstanding privacy related actions are required for the UE (e.g. no privacy notification and/or privacy verification interaction with the UE). QoS requirements must also be satisfied for the non-executed location requests. 5.7.4	Combining location requests by an AMF An AMF may combine concurrent 5GC-MT LR, 5GC-MO LR and 5GC-NI LR location requests once any needed privacy related actions (e.g. UE notification and verification) have been performed for each 5GC-MT LR. (i.e. AMF may decide to not execute multiple positioning procedures for the concurrent location requests) QoS requirements must also be satisfied for the non-executed location requests. 5.7.5	Combining location requests by an LMF An LMF may combine concurrent location requests for the same target UE provided QoS requirements can be satisfied for the non-executed location requests. 5.7.6	Combining location requests by a UE A UE may combine concurrent location requests provided QoS requirements can be satisfied and provided any positioning procedures with an LMF remain supported according to the positioning protocol.
