# 9. Vue 3 single-page app with OpenLayers

Date: 2026-10-03

## Status

Proposed (records the baseline 1.7.1)

**TOGAF Phase:** C (Application Architecture)
**Decision Maker(s):** Project owner (kvelev)
**Stakeholders:** HQ operator, command post team, contributors
**Principles:** upholds TP-01 (no server-side rendering service, assets can be local), BP-02; trades off TP-01
partly while online basemaps are the default (R-04)

## Context

The operator needs a live map with markers, trails, alarms and layers (fire data, offline tiles), in Bulgarian
and English, on a laptop and on a wall display. Contributors include AI agents, so the stack should be common
and well documented.

## Decision

We will build the client as a **Vue 3 single-page app** (`<script setup>`, Pinia, vue-router, axios, Vite), with
**OpenLayers** for the map, plain CSS with design tokens, and every UI string in `i18n/en.js` and `i18n/bg.js`.
The SPA talks only to the backend (REST and `/ws`), except for optional online tile and weather layers.

## Consequences

**Positive:**
- OpenLayers handles XYZ tiles, vector layers and projections without a vendor key.
- A built SPA is static files: it can be served by the backend or any local web server (Phase D).

**Negative / Trade-offs:**
- Today it runs from the Vite dev server (R-11).
- Online basemap URLs are in the client (R-04). The OpenWeatherMap key was too, until the backend weather proxy (R-05).
- Front-end changes follow the project's design workflow (dedicated design agent), which adds a step.

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **Vue 3 + OpenLayers** | As built | Small, common, strong GIS | |
| React + Leaflet / MapLibre | Other common stack | Large ecosystem | Rewrite; MapLibre favours vector tiles |
| Server-rendered pages | Templates from FastAPI | No build step | Poor fit for a live map |

## Related

- [application-architecture.md](../application/application-architecture.md) Section 3.2
