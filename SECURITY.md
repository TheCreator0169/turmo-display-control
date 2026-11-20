# Security Policy

## Supported versions

Only the **latest release** gets security fixes. Please update first (About > Update, or the
[Releases](https://github.com/TheCreator0169/turmo-display-control/releases) page) and check that the problem is still there.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private reporting: open the **Security** tab of this repository, then **Report a vulnerability**
(<https://github.com/TheCreator0169/turmo-display-control/security/advisories/new>). Include:

- the TURMO version (About page) and your Windows version;
- what you did, what you expected, what happened;
- how it could be abused, if you know.

This is a one-person project: expect an answer within about 7 days, and a fix or a decision as soon as I can. I will credit you
in the release notes unless you prefer not to be named.

## What TURMO does that matters for security

- **An elevated task.** The installer registers a scheduled task, "TURMO CpuTemp Helper", that starts when you sign in and runs
  hidden with administrator rights. It only reads the CPU temperature (through LibreHardwareMonitor and the PawnIO driver) and
  answers the app on the local machine. The uninstaller removes it. Reports about this task (privilege escalation, a way for another
  program to make it do more, wrong file permissions on its folder) are the most welcome.
- **One network call, only when you ask.** The Update button in About asks GitHub for the latest release. If a newer one exists it
  downloads the installer from this project's release address and checks its SHA-256 against the `SHA256SUMS.txt` of the same
  release before starting it. The hash is published next to the file, so it catches a damaged download, not a hijacked account.
- **No telemetry.** Nothing else leaves your PC. Settings and your own themes are in `%APPDATA%\TURMO`; logs in
  `%LOCALAPPDATA%\TURMO\logs`.
- **Not code-signed yet.** Windows SmartScreen may warn on the installer. Compare the file with `SHA256SUMS.txt` of its release.

## Out of scope

- Problems that need an attacker who already has administrator rights on the PC.
- Vulnerabilities of the PawnIO driver, LibreHardwareMonitor or other third-party parts: please report them to their projects
  (the list is in `THIRD_PARTY_NOTICES.md`), and tell me if TURMO makes the impact worse.
- Reports from automated scanners without a way to reproduce the problem.
