# Security Policy

Athena stores personal information about library patrons, so we take security reports seriously.
This document explains how to report a problem, what to expect, and how Athena is designed to
protect the data it holds.

Last reviewed: 2026-11-16.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately in either of these ways:

1. **GitHub private reporting (preferred).** Go to the repository's **Security** tab and choose
   **Report a vulnerability**:
   https://github.com/TechnoEquinox/Project-Athena/security/advisories/new
2. **Email:** `connorb@cheshirect.gov`

Please include what you can of the following:

- What the problem is and why you think it is a vulnerability
- Steps to reproduce it, or a short proof of concept
- The Athena version (shown in the page footer, or the `VERSION` file) and how it was installed
- What an attacker could do with it, and what they would need first (for example, a signed-in
  account, or network access to the server)

**Never include real patron data**, real passwords, keys, or the addresses of a library's server in
a report. Use made-up records.

## What to expect

Athena is maintained by a small number of volunteers, so these are targets, not guarantees:

- We will acknowledge your report within **7 days**.
- We will tell you whether we consider it a vulnerability, and our plan, within **14 days**.
- We aim to release a fix for serious issues as quickly as we responsibly can, and will keep you
  updated while we work.
- We practice **coordinated disclosure**. Please give us up to **90 days** from your report to
  fix the issue before you discuss it publicly. If it is being actively exploited, we will move
  faster and may ask you to coordinate on timing.
- When a fix is released we publish a security advisory describing the issue and the fix, and
  we credit you by name unless you ask us not to.

## Scope

**In scope**

- The Athena application: the API, the web interface, the command-line tools, and the database
  migrations
- The installer and any maintenance tooling shipped in this repository
- The default configuration the installer produces

**Out of scope**

- A library's own server, network, or building: physical access, weak passwords chosen by staff,
  an unpatched operating system, or a misconfigured firewall
- Social engineering of staff or maintainers
- Attacks that require an attacker to already control the server or an administrator account
- Denial-of-service through sheer traffic volume
- Reports from automated scanners that show no real impact (for example, a missing header with
  no demonstrated attack)
- Vulnerabilities in third-party software that are already public and do not affect Athena as
  configured. Please report these to the project concerned, and tell us if you believe Athena's
  use of the component is exploitable.

Putting Athena directly on the public internet is **not a supported configuration** (see
"Assumptions" below). Reports that only matter in that setup are welcome, but may be handled at a
lower priority.

## Testing safely

We will not take action against anyone who finds and reports a problem in good faith and follows
these rules:

- Test only against your own installation, never against a library's real system or a real
  patron's data
- Do not access, change, or keep data that is not yours
- Stop testing and tell us if you reach real patron data by mistake
- Do not disrupt other people's use of a system

## Supported versions

Until Athena reaches a stable 1.0 release, only the **latest release** receives security fixes.
Please update to it before reporting, if you can.

## How Athena is designed to be secure

### Assumptions

Athena is designed for a library that:

- Runs it on a server in a **physically secured room**, reachable only on the library's **internal
  network** and not from the internet
- Gives each staff member their own account
- Is responsible for the server itself: the operating system, the network, backups, and who has
  physical and administrative access

**Disk encryption is not set up by Athena.** The design relies on physical security of the
server. If your server room is not locked down, or if drives leave your control (repairs, warranty
swaps, recycling),