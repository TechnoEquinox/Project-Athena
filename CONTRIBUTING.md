# Contributing to Athena

Athena is free software under the GNU Affero General Public License v3.0 or later (see LICENSE).

## Sign your commits

By contributing you certify the Developer Certificate of Origin (https://developercertificate.org/):
that you wrote the work, or have the right to submit it, under this project's license. Add a
sign-off to every commit:

    git commit -s -m "Your message"

This appends a line like `Signed-off-by: Your Name <you@example.com>`. If your employer may own
work you do, get their approval first.

## Before you send a change

- Run the tests. Back end: `sudo docker compose run --rm --build test`.
  Front end: `sudo docker compose run --rm web npm test`.
- New behavior comes with tests.
- Never put real patron data, passwords, keys or addresses in an issue, a pull request or a test.
- Report security problems privately, not in a public issue. SECURITY.md will say how.