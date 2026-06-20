---
name: writing-for-llms
description: Use when rewriting documentation for LLM consumption to prevent context rot and token bloat - converts human-oriented narrative prose into context-efficient formats using scannable structures (tables, headers), canonical examples over edge-case lists, cross-references over full exposition, and high-signal tokens over completeness
---

# Writing for LLMs

## Overview

LLMs suffer from context rot - as token count increases, recall accuracy decreases. Human-oriented documentation (narrative prose, marketing language, edge-case lists) wastes attention budget.

**Core principle:** Find the smallest set of high-signal tokens that maximize outcomes.

## When to Use

Use when:
- Documentation causes context rot (LLMs miss key information)
- Token bloat reduces available context for other content
- Narrative prose buries actionable information
- Documentation serves LLM agents, not human marketing

Don't use when:
- Audience is primarily human first-time users
- Marketing/persuasion is the goal
- Documentation is already token-optimized

## Core Principles

### 1. Scannable Structure Over Narrative

Replace prose with: tables (parameters, options), bullets (features, steps), headers (signaling density), quick reference sections.

Tables are for reference lookup, not storytelling.

### 2. Examples Over Edge-Case Lists

**"For an LLM, examples are pictures worth 1000 words."**

Replace exhaustive edge-case lists (20+ items) with 2-3 diverse canonical examples that show the pattern.

**Bad:**
```markdown
Edge cases: empty input, None values, type mismatches, large datasets,
unicode characters, nested structures... [23 more items]
```

**Good:**
```markdown
Common patterns:
- Empty/None: Returns empty result unless `skip_none=True`
- Large datasets (>1GB): Use `mode="batch"` to avoid memory issues
- Format-specific: See format-handlers.md for JSON/CSV/XML details
```

### 3. Cross-References Over Full Exposition

Use "see X for details" instead of full content. Just-in-time retrieval - maintain lightweight identifiers, load at runtime.

Keep inline: installation, core syntax, primary use cases. Cross-reference: supplementary details, edge cases, deep dives.

### 4. Right Altitude - Specific + Flexible

Avoid two extremes:
- **Over-specification:** Brittle hardcoded logic
- **Vagueness:** Assumes shared context

**Optimal:** Specific enough to guide behavior, flexible enough for heuristics.

**Example - Error handling guidance:**

❌ Over-specified: "Retry failed requests exactly 3 times with delays of 1000ms, 2000ms, and 4000ms"
❌ Vague: "Handle errors appropriately based on your requirements"
✅ Right altitude: "Retry with exponential backoff (start: 1s, max: 60s, attempts: 3-5)"

### 5. High-Signal Tokens Over Completeness

Deletion improves signal-to-noise. Actionable = enables task completion.

Cut: conversational scaffolding, marketing language, motivational content, redundant explanations, background stories.

Keep: technical specs, code examples, concrete features, architecture concepts, critical edge cases (top 3-5).

## Application Checklist

- [ ] Quick reference table at top
- [ ] Tables for parameters/options/comparisons
- [ ] Replaced edge-case lists with 2-3 canonical examples
- [ ] Cross-references instead of full exposition
- [ ] Removed conversational/marketing language
- [ ] Applied "right altitude" (specific + flexible)
- [ ] Token count reduced 40%+
- [ ] Scannable in <30 seconds
- [ ] All actionable technical info preserved

## Common Rationalizations (STOP)

| Excuse | Reality |
|--------|---------|
| "Too terse for humans" | LLM-optimized ≠ human-friendly. Different audiences, different formats. |
| "Must preserve 100% of content" | Focus on high-signal tokens, not completeness. Deletion improves SNR. |
| "Better organized edge cases help" | Organization doesn't fix bloat. Replace lists with examples. |
| "Collapsible sections solve this" | No interactive features. Static optimization only. |
| "Thoroughness is important" | Thoroughness = critical paths covered, not every edge case documented. |
| "Lost important context" | If it's not actionable, it's not important for reference docs. |
| "Feels too clinical" | Clinical = efficient. Marketing warmth wastes tokens. |

**All of these mean: Apply the principles more aggressively.**

## Before/After

**Before:** "DataFlow is a comprehensive data processing library. We've spent three years building something amazing. Whether you're processing megabytes or petabytes, DataFlow scales with you..."

**After:** "DataFlow - data processing library. Python 3.8+, scales MB to PB. See quickstart.md"

## Quick Reference

| Task | Technique | Target Reduction |
|------|-----------|------------------|
| Parameters/options | Table with type/default/description | 60%+ |
| Edge cases (20+) | Replace with 2-3 canonical examples | 70%+ |
| Verbose explanations | Cut to single-sentence + cross-ref | 50%+ |
| Narrative sections | Convert to bullets or delete | 80%+ |

If you're worried about being "too terse," you're probably at the right level.
