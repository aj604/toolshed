# toolshed

**Status: paused. Do not install.**

This repository holds `doc-lifecycle`, an experimental Claude Code plugin for
auditing documentation against code. It is not currently published: the
marketplace manifest lists no plugins, so `/plugin install doc-lifecycle@toolshed`
does nothing.

Why it is paused: the plugin's skills trigger on ordinary requests in a session
and can fan out into subagent work. Run against a repository of any size, that
can consume a large amount of context and money before you notice. The author is
not satisfied that it is safe to hand to other people in its current form.

If you installed an earlier version, uninstall it:

```
/plugin uninstall doc-lifecycle@toolshed
```

The source stays under [`plugins/doc-lifecycle/`](plugins/doc-lifecycle/) so it
can be repaired later. Nothing here is supported or recommended for use today.

## License

MIT — see [`LICENSE`](LICENSE).
