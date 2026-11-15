---
title: '3GPP 21111-f20: Contents of the Elementary Files'
slug: 3gpp-21111-f20-contents-of-the-elementary-files
category: concepts
aliases: []
tags:
- information
- shall
- network
- service
- entry
- usim
- support
- call
- entries
- phone
- 3gpp
- contents
- elementary
- storage
sources:
- 2026-11-14-telequad-w01-15.md
- 2026-11-14-telequad-w02-15.md
- 2026-11-14-telequad-w03-15.md
- 2026-11-14-telequad-w04-15.md
- 2026-11-14-telequad-w05-15.md
- 2026-11-14-telequad-w06-15.md
- 2026-11-14-telequad-w07-15.md
- 2026-11-14-telequad-w08-15.md
- 2026-11-14-telequad-w09-15.md
- 2026-11-14-telequad-w10-15.md
created_at: '2026-11-14T05:19:09Z'
updated_at: '2026-11-14T05:20:20Z'
revision_count: 10
confidence: high
summary: "10\tContents of the Elementary Files 10.1\tUSIM information storage requirements\
  \ The USIM shall contain information elements for 3G network operations. The USIM\
  \ may contain inform..."
---

# 3GPP 21111-f20: Contents of the Elementary Files

10	Contents of the Elementary Files 10.1	USIM information storage requirements The USIM shall contain information elements for 3G network operations. The USIM may contain information elements related to the subscriber, 3G services and home environment or service provider related information. The UICC shall provide storage capability for the following: -	UICC related information: In addition, the USIM shall manage and provide storage for the following information in accordance with the security requirements of clause 5: 10.2	Phone Book A Phone Book entry consists of a record in an ADN file and, optionally, additional records which are placed in different EFs. In the latter case, a mechanism shall be defined to link all records in the same Phone Book entry. These features shall be supported by the ME while their support by the UICC is optional. 10.2.1	Support of two name fields per entry The support of two name fields per entry shall be specified to allow, for example, for two different representations of the same name (for example, in Japanese characters and in Latin characters).

## Evolution & Synthesized Updates

- **[2026-11-14 | 2026-11-14-telequad-w04-15.md]** (3GPP 21111-f20: Contents of the Elementary Files: Extended Procedures & Parameters): 10.2.2	Support of multiple phone numbers per entry The support of multiple phone numbers per entry shall be specified, for example, office, home, fax, mobile or pager. In addition to that, information for identifying those attributes are needed. 10.2.3	Support of email address The support of email addresses linked to Phone Book entries shall be specified. In addition to that, information for identifying these addresses is needed. 10.2.4	Support of user definable groupings The specification shall support the grouping of Phone Book entries into groups defined by the user, for example, business and private. 10.2.5	Support of hidden entries The specification shall support means of marking Phone Book entries as "hidden". 10.2.6	Number of entries The specification shall support storage of at least 500 entries. 10.3	Storage of call details The specification shall support provision of storage for call detail information. The call detail information consists of the following attributes: Call detail attributes are optional. A value to mark them as "undefined" shall be available.
