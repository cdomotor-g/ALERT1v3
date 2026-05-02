# Agentic Refactor Plan (living)

Goal: reduce monolith friction and improve safe, fast iterative development.

## Priority backlog

1. Split `webui/server.py` into route modules
2. Shared receiver-aware JS fetch client
3. Shared page bootstrap helpers
4. Role-gated UI context endpoint
5. Template fragment reuse
6. JSON repository layer
7. Dev safety script suite
8. Unified role->service manifest
9. `/control` as canonical config manager
10. Prune deprecated artifacts

## Current execution track

### Track A — modular server routes (in progress)
- [ ] Introduce `webui/routes/` package
- [ ] Move control APIs first (`/api/control/*`)
- [ ] Keep behavior parity via thin delegation from `server.py`

### Track B — shared receiver client JS
- [ ] Create `webui/static/shared/receiver_client.js`
- [ ] Migrate packets page
- [ ] Migrate forensics page

## Guardrails
- Keep commits small and testable
- Preserve endpoint compatibility
- Prefer additive changes before deletions
- Push every commit to `main`
