# Project-Athena (v0.1.0)

Project Athena is the open source CRM tooling for Connecticut Public Libraries in their work to provide Digital Navigation to their community. This tool allows staff in a libraries technology department to track unique clients across multiple appointments at different locations, and provide statistics, KPIs, and other useful metrics used for staffing, securing grants for future funding, and more. 

- Runs on Ubuntu Server inside the library's LAN (Local Area Network)
- No tracking, registration, or phoning home to third party companies or services
- Sign-in uses passwords plus two-step verification through your preferred TOTP authentication app
- Free for any library to use, change, and share (AGPL-3.0, see License)
- **Status: Early release (0.1.0).** Installation works, but **built-in backups are still a work in progress**. Please do not store irreplaceable data until you have a backup plan.

## What You Need

| Required |  Why |
| -------- | -------- |
| Server    | A computer running Ubuntu Server 24.04 or newer (a small PC is fine). At least 2 CPU cores, 2 GB memory (4 GB better), 20 GB free disk.     |
| Network    | A wired connection and a fixed IP address for the server (ask your IT contact for a "DHCP reservation").     |
| Where    | A physically secure spot (locked room). Patron records are stored on it. The disk is not encrypted by default; see SECURITY.md.     |
| A person    | Someone comfortable typing commands over SSH. You do not need to be a programmer.     |

## Install
After booting Ubuntu Server, you have two different options:
1. Using physical access to the server with a mouse and keyboard
2. Using a SSH connection (this requires knowing the IP address of the server ahead of time. You can find the IP address of the server by running `ifconfig` directly on the server. Look the IP address under eth0.)

Next, copy and paste these lines:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/TechnoEquinox/Project-Athena.git
cd Project-Athena
sudo ./install.sh
```

The installer asks a few plain questions and explains each step as it goes:

1. Address for Athena: what staff will type in their browser. The server's IP address is suggested; use that if you are unsure.
2. Time zone and fiscal year start month (used in reports).
3. Firewall: it limits access to your library network. It checks first that it will not cut off your current connection.

It takes about 10 minutes. It is safe to run again if something stops it. It never replaces your existing secret settings.
When it finishes, it prints your next steps. They are repeated below.

**WORK IN PROGRESS**

## License
**AGPL-3 or later**
Athena is free software: you can redistribute it and/or modify it under the terms of the GNU
Affero General Public License as published by the Free Software Foundation, either version 3 of
the License, or (at your option) any later version. See [LICENSE](LICENSE).

It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY, without even the
implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

If you modify Athena and run your version for other people to use over a network, the AGPL
requires you to offer those users the source code of your modified version.

Athena stores personal information about library patrons. Whoever runs it is responsible for
securing that information and for following the laws and policies that apply to them.
