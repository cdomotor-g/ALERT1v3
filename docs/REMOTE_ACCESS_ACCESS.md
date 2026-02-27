# Remote Access Governance (Cloudflare Access + Tailscale Fallback)

This runbook covers multi-user authenticated access to FW-LAB.

## Baseline architecture

- Public URL: `https://fwlab.floodwarning.net`
- Transport: Cloudflare Tunnel (`cloudflared`) to `http://127.0.0.1:8088`
- Identity gate: Cloudflare Access application policy (email/group allowlist)
- Fallback admin path: Tailscale private URL

## Security requirements

1. Port 8088 must not be publicly open.
2. Cloudflare Access policy must enforce authenticated allowlist access.
3. Receiver/admin controls should only be available to operator/admin users.

## Onboarding a collaborator

1. Add collaborator email to Cloudflare Access allow policy for `fwlab.floodwarning.net`.
2. Ask collaborator to test login and open `/events` and `/trends`.
3. Confirm denied access for non-allowlisted test account.

## Offboarding

1. Remove collaborator email/group from Access policy.
2. Invalidate active sessions if needed from Access dashboard.
3. Verify denied access with removed account.

## Emergency shutdown / rollback

- Disable tunnel service:
  ```bash
  sudo systemctl disable --now cloudflared
  ```
- Keep local/Tailscale operations alive.
- Re-enable when safe:
  ```bash
  sudo systemctl enable --now cloudflared
  ```

## Audit checklist

- Access policy includes explicit allowlist
- No broad "allow everyone" production rule
- 8088 public exposure remains blocked
- cloudflared service healthy and managed
