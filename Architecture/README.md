# Bee With Me architecture documentation

Architecture of Bee With Me, an offline LoRa people tracker for rescue and volunteer operations, written
along the TOGAF ADM. Everything is Markdown with Mermaid diagrams.

## Start here

| If you want to | Read |
|------------------|------|
| understand the system and its boundaries | [Architecture.md](Architecture.md) |
| know the rules every change must respect | [principles/architecture-principles.md](principles/architecture-principles.md) |
| know what the system does for the business | [business/business-architecture.md](business/business-architecture.md) |
| know the data, its classification and lifetime | [data/](data/) |
| know the components and interfaces | [application/](application/) |
| know the technology, operations and coding rules | [technology/](technology/) |
| run the system as an administrator (Bulgarian) | [guides/admin-guide.md](guides/admin-guide.md) |
| see what may come later | [roadmap/future-capabilities.md](roadmap/future-capabilities.md) |
| know why something is built the way it is | [decisions/0000-README.md](decisions/0000-README.md) (ADR index) |

## For coding agents

1. Read the principles and run their **How to check** table against your change; follow
   [technology/engineering-standards.md](technology/engineering-standards.md) and cite `ES-xx` rules.
2. Search the ADR index before introducing a technology, pattern or external connection; if your change
   contradicts an accepted ADR, stop and propose a new ADR instead.
3. Cite principle IDs (`BP-01`, `DP-02`, `TP-03`) and ADR numbers in plans, commits and pull requests.
4. `⚠️` lines are open questions for the owner: do not decide them yourself; mention them in your report.

## Folder map

```
Architecture/
├── README.md                         this index
├── Architecture.md                   main document, one section per ADM phase (stable)
├── principles/
│   └── architecture-principles.md    principles BP / DP / TP with checks
├── business/
│   └── business-architecture.md      capabilities, processes, rules, gaps (mutable)
├── data/
│   ├── domain-model.md               entities and relationships (mutable)
│   ├── data-classification.md        classification, readers, lifetime per store (mutable)
│   ├── schema-core.md                core tables (mutable; migrations win)
│   └── schema-fire.md                fire tables (mutable; migrations win)
├── application/
│   ├── application-architecture.md   containers, components, flows, auth (mutable)
│   ├── api-contracts.md              REST, WebSocket, hardware, external feeds (mutable)
│   └── modular-monolith.md           target modules (vertical slices), outbox, architecture tests (mutable)
├── technology/
│   ├── technology-architecture.md    catalogue, topology, ports, operations (mutable)
│   ├── engineering-standards.md      rules ES-01 to ES-34 (mutable)
│   └── nfr-traceability.md           measures and principles to mechanisms and checks (mutable)
├── decisions/
│   ├── 0000-README.md                ADR index and how to write one
│   └── NNNN-short-title.md           one ADR per decision (adr-tools layout)
├── governance/
│   └── risk-register.md              risks (mutable)
├── guides/
│   └── admin-guide.md                administrator guide, Bulgarian (mutable)
└── roadmap/
    ├── future-capabilities.md        catalogue FC-xx, input to Phase E (mutable)
    └── fc-NN-*.md                    assessment of one future capability (FC-01: assistant, hardware)
```

Supporting documents (data model, API contracts, technology catalogue, engineering standards, roadmap)
are added as their phases are written.

## Markers used in these documents

> ⚠️ **Requires stakeholder input:** an open question for the owner.

> ⚠️ **Requires technical clarification:** a gap the developers must close.

> 📝 **Assumption:** stated, to be validated.

## Status

| Phase | Status |
|-------|--------|
| Preliminary | Draft |
| A: Architecture Vision | Draft |
| B: Business Architecture | Draft |
| C: Data + Application | Draft |
| D: Technology + engineering standards | Draft |
| E to H | Not started |
