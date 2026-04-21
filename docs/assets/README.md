# docs/assets/

Static assets for the landing site and documentation.

## Planned additions

- `demo.gif` — 30-60 second recording of the first-memory flow from
  `docs/QUICKSTART.md`. Referenced from `docs/en/index.html` and
  `docs/zh/index.html`. Until the GIF exists, both hero sections
  render a dark terminal block with the same transcript as a fallback.

## How to record the demo

```bash
# Use asciinema or t-rec. Target ≤60s, ≤1MB after palette optimization.
brew install t-rec
cd /tmp && mkdir engram-demo && cd engram-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -e /path/to/engram/cli
t-rec --output demo.gif -- bash -c '
set -e
engram init --name=acme-platform
sleep 1
engram memory add --type=feedback --enforcement=mandatory \
  --name="confirm before push" \
  --description="never push without explicit go-ahead" \
  --body="Ask before pushing.\n\n**Why:** prior force-push lost work.\n\n**How to apply:** every git push."
sleep 1
engram memory search "push"
sleep 1
engram validate
sleep 1
engram status
'
# Move output in when done:
mv demo.gif /path/to/engram/docs/assets/demo.gif
```

Keep the recording **pure** — no commentary overlay, no interactive
prompts, just the CLI doing its job. The point is to show that the
steps on `docs/QUICKSTART.md` really take five minutes and really work.
