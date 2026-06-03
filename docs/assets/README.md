# README diagram assets

The architecture diagram in [README.md](../README.md) is maintained as **Mermaid** in the repo (renders on GitHub).

To export PNGs locally (optional):

```powershell
npx -y @mermaid-js/mermaid-cli -i README.mmd -o docs/assets/architecture.png
```

Keep Mermaid as the source of truth unless you intentionally commit refreshed PNGs.
