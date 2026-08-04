## What this PR does

<!-- one or two sentences -->

## Accountable review and AI assistance

- [ ] I name the human maintainer accountable for this change in the PR.
- [ ] I disclosed AI assistance (or explicitly wrote “none”), including whether
      it touched code, tests, benchmark questions/golds, or documentation.
- [ ] I reviewed generated output against primary sources and repository
      contracts; tool output is not treated as review evidence.
- [ ] Any benchmark gold has independent experienced-DM review, or is clearly
      labeled as an engine-derived consistency fixture rather than independent
      rules-accuracy evidence.

## Provenance checklist (required)

- [ ] All rule content in this PR derives from the official SRD 5.2.1 document
      (or from an adapter whose manifest declares its own licensed source).
- [ ] Every new rule atom carries a citation with a **verbatim quote**.
- [ ] No content from the Player's Handbook, D&D Beyond, Sage Advice,
      third-party books, or homebrew — even paraphrased.
- [ ] Kernel changes contain zero game vocabulary (the lint will check anyway).
- [ ] New verdict paths cite; edges return exit 2 rather than guessing.
