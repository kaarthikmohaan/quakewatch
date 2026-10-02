# Accessibility

QuakeWatch is a small data-engineering project. People use it by reading its
documentation on GitHub, running Python commands in a terminal, and reading
SQL results. It has no website or graphical interface of its own.

We want anyone to be able to read the documentation, run the commands, and
contribute, including people who use screen readers, keyboard-only navigation,
magnification, or translation tools. This page explains what we aim for, what
we have and have not checked, and how to tell us about a barrier.

## Priorities

- **Readable documentation.** Documents use real headings, descriptive link
  text, plain language, and text instead of images. Diagrams are written in
  Mermaid, so their source is readable text, and the README describes the
  pipeline in words below its diagram.
- **Terminal output that works as text.** Commands print plain text that does
  not rely on colour, animation, or special symbols to convey meaning.
- **Information that does not depend on visuals.** Results are given as
  numbers and words in the text, not only in charts or screenshots.

These are goals, not a verified conformance claim. QuakeWatch has not had a
formal accessibility evaluation against WCAG or any other standard.

## Contributor expectations

When you change documentation or anything a person reads, please:

- Use Markdown headings in order and avoid skipping levels.
- Write link text that makes sense on its own; avoid "click here".
- Add alt text to any image, and give the same information in the text.
- Do not use colour, emoji, or symbols as the only way to convey meaning.
- Keep tables simple, with a header row, and prefer lists for long content.
- Keep terminal output readable as plain text.

No automated accessibility checks run in CI today. Mention any accessibility
effect of a change in your pull request.

## Reporting accessibility issues

If something in QuakeWatch is hard or impossible for you to use, please tell
us. You can:

- [Open an issue](https://github.com/kaarthikmohaan/quakewatch/issues/new/choose)
  and mention "accessibility" in the title, or
- Email the maintainer at karthik12mohan@gmail.com if you prefer not to post
  publicly.

It helps to include what you were trying to do, the page or command involved,
what happened, and your browser, operating system, and any assistive
technology you use. Screenshots or recordings are optional, and you never need
to share anything about a disability.

### Severity

The maintainer assigns severity during triage; you do not need to.

- **Blocking:** you cannot complete a task at all, such as following the
  quickstart or reading a key document.
- **Serious:** you can complete the task only with significant extra effort or
  outside help.
- **Minor:** the task is possible but awkward or confusing.

### How we respond

QuakeWatch is maintained by one person in their own time. We aim to
acknowledge reports within 7 days and to fix blocking problems first. Where a
fix will take time, we will suggest a workaround if one exists, and you are
welcome to check the fix once it is ready.

## Ownership and maintenance

The project maintainer, [@kaarthikmohaan](https://github.com/kaarthikmohaan),
is responsible for accessibility, including reviewing reports and keeping this
page accurate. This page is reviewed whenever the documentation or command-line
tools change significantly. If maintenance passes to someone else, they take
over these responsibilities.

## Supported environments

- **Documentation:** read on github.com, which handles its own accessibility.
  We have not tested the documentation with specific screen readers.
- **Command-line tools:** run with Python 3.12 in a terminal. Tested on macOS
  locally and on Ubuntu in GitHub Actions. Windows has not been tested.
- **Snowflake and Snowsight:** third-party services outside this project's
  control.

## Known limitations

- Some documents, such as the design page, the operations reference, and the
  results evidence log, are long and contain many numbers in dense paragraphs,
  which can be tiring to follow with a screen reader or translation tool. The
  [results summary](docs/results.md) gives the main figures in short tables.
- The rendered Mermaid diagrams in the README and data dictionary are graphics.
  Screen readers may not describe them; the surrounding text and the data
  dictionary tables carry the same information.
- Some tables are wide and may need horizontal scrolling on small screens or
  at high magnification.
- The supported-versions table in the security policy uses check-mark and cross
  emoji, which screen readers announce by name.
- Running the warehouse needs a Snowflake account and the Snowsight web
  interface, whose accessibility we do not control.

No testing with assistive technology has been done yet, so other barriers may
exist. Please report any you find.

## Feedback and improvements

Suggestions for this page or for the project's accessibility practices are
welcome in [GitHub Discussions](https://github.com/kaarthikmohaan/quakewatch/discussions)
or as an issue. If something is blocking you right now, use the reporting
steps above so it is handled first.
