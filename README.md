# Project-Athena (v0.1.0)

Project Athena is the open source CRM tooling for Connecticut Public Libraries in their work to provide Digital Navigation to their community. This tool allows staff in a libraries technology department to track unique clients across multiple appointments at different locations, and provide statistics, KPIs, and other useful metrics used for staffing, securing grants for future funding, and more. 

- Runs on Ubuntu Server inside the library's LAN (Local Area Network)
- No tracking, registration, or phoning home to third party companies or services
- Sign-in uses passwords plus two-step verification through your preferred TOTP authentication app
- Free for any library to use, change, and share (AGPL-3.0, see License)
- **Status: Early release (0.1.0).** Initial public release of the project, but **built-in backups are still a work in progress**. Please do not store irreplaceable data until you have a backup plan. **Installer files will be added in a future release**.

### Table of Contents
- [What You Need](#what-you-need)
- [Install](#install)
- [After install](#after-install)
  - [1. Create the first administrator](#1-create-the-first-administrator)
  - [2. Copy the certificate to staff computers](#2-copy-the-certificate-to-staff-computers)
  - [3. Sign in and set up two-step verification](#3-sign-in-and-set-up-two-step-verification)
  - [4. Set up your library](#4-set-up-your-library)
  - [5. Save your secrets offline](#5-save-your-secrets-offline)
- [Everyday commands](#everyday-commands)
- [Backups](#backups)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

## What You Need

| | |
|---|---|
| **Server**    | A computer running Ubuntu Server 24.04 or newer (a small PC is fine). At least 2 CPU cores, 2 GB memory (4 GB better), 20 GB free disk.     |
| **Network**    | A wired connection and a fixed IP address for the server (ask your IT contact for a "DHCP reservation").     |
| **Where**    | A physically secure spot (locked room). Patron records are stored on it. The disk is not encrypted by default; see [SECURITY.md](SECURITY.md).     |
| **Employee**    | Someone comfortable typing commands over SSH or locally on the server. You do not need to be a programmer to complete the setup.     |

## Install
After booting Ubuntu Server, you have two different options:
1. Using physical access to the server with a mouse and keyboard.
2. Using a SSH connection (this requires knowing the IP address of the server ahead of time. You can find the IP address of the server by running `ifconfig` directly on the server. Look the IP address under eth0).

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

## After Install

### 1. Create the first administrator
```bash
athena create-admin
```

You will be asked for a name and a password (12+ characters are required). Anything you type for the password is hidden. If you only want one person to have administration access, you can use the name ***admin***.

### 2. Copy the certificate to staff computers

Athena uses HTTPS with its **own private certificate**, so staff browsers show a warning until they trust it. The installer saves the certificate in your home folder on the server as **`athena-root-ca.crt`**. You can always re-create the certificate and see its fingerprint by running `athena cert`.

**To get the file off the server**, run this on the staff PC you wish to install the certificate on:

```bash
scp YOUR_USERNAME@SERVER_ADDRESS:athena-root-ca.crt .
```

You can also use any SFTP program (like WinSCP, FileZilla, Cyberduck). To confirm the file was not altered on the way, compare its fingerprint with the one the installer printed:

(Mac or Linux client)
```bash
openssl x509 -in athena-root-ca.crt -noout -fingerprint -sha256
```

(Windows client)
```bash
certutil -dump athena-root-ca.crt
```

Compare the SHA-256 values to make sure they match what is shown on the Ubuntu Server. If the values do not match, do not use the certificate and try again.

**Install it on each staff computer**

- **Windows (Edge / Chrome):** double-click the file → *Install Certificate* → *Local Machine* (needs admin) → *Place all certificates in the following store* → **Trusted Root Certification Authorities** → Finish. Restart the browser.
- **Mac (Safari / Chrome):** double-click the file (opens Keychain Access) → add to **System** → double-click the certificate → expand *Trust* → set *When using this certificate* to **Always Trust**.
- **Firefox (any computer):** Settings → Privacy & Security → *View Certificates* → *Authorities* → *Import* → tick *Trust this CA to identify websites*.
- **Library-managed PCs:** your IT team can push the file out with Group Policy or their device manager.

Once the certificate is installed, open your web browser and navigate to `https://YOUR_SERVER_IP_ADDRESS/`. The padlock should show no warnings and should verify the connection is secure.

### 3. Sign in and set up two-step verification

Sign in with the administrator account you created during the install. You will be guided to scan a QR code with an authenticator app (Google Authenticator, Microsoft Authenticator, Authy, Apple Passwords, etc.) and given **recovery codes**. **Print or write the recovery codes down and keep them somewhere safe.**

### 4. Set up your library

In the **Admin** page, add your **locations**, **navigators**, and **users**. There are three roles with different access policies:

1. *admin* - Can access everything, including server administration settings
2. *manager* - Has read-only access, cannot make any changes
3. *navigator* - Can read/write clients, appointments, and calls for day-to-day usage

### 5. Save your secrets offline

On the Ubuntu Server, copy `opt/athena/.env` to a USB and keep that USB in a secure location. It contains the database password and the key that protects saved 2FA secrets. **If you lose it and the server dies, all the data in the database cannot be recovered!** Do not rename or change this file in any way. 

**TODO:** Add instructions for saving the file to a USB or using scp.

## Everyday commands

These commands can be run on the server. Each has its own unique function that helps to make managing the server easy:

| Command | What it does |
|---|---|
| `athena status` | Shows whether everything is running |
| `athena logs` | Recent activity (add `db` or `caddy` for other parts) |
| `athena restart` | Restarts Athena (data is kept) |
| `athena create-user` | Adds a staff account |
| `athena unlock-user NAME` | Unlocks someone who is locked out |
| `athena reset-totp NAME` | Resets someone's 2FA (lost phone) |
| `athena cert` | Re-saves the certificate and shows its fingerprint |
| `athena version` | Shows the installed version |

Old deleted records are permanently removed after 30 days, and expired sessions are cleaned up, automatically each night.

Athena is designed so most of these commands are abstracted through the web interface (accessible only by admin users), so you don't have to constantly drop to the command-line to access these functions.

## Backups

**This feature is not finished yet.** Instructions for completing backups will be made available on a later date.

## Troubleshooting

- **Browser says the connection is not private:** the certificate is not installed on that computer yet (see above).
- **Page will not load at all:** run `athena status`. If `api` is restarting, run `athena logs`.
- **Cannot reach the server after it restarted:** its IP address may have changed (DHCP). Ask IT for a fixed address.
- **The installer stopped:** it tells you which step failed and writes details to `/var/log/athena-install.log`. Run it again; it picks up where it left off.

When asking for help, include the last lines of that log. **Remove any passwords first.**

## Security

Please read [SECURITY.md](SECURITY.md) for how to report a vulnerability privately and for all of the assumptions made when running Athena.

This project's repository is scanned with Dependabot, which automatically reports security vulnerabilities in the packages that Athena requires. Make sure you are always running the most up-to-date version of Athena to get the latest security patches. 

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute to Athena.


## License

Project Athena is licensed under the **GNU Affero General Public License v3.0 or later** (AGPL-3.0-or-later). See [LICENSE](LICENSE).

In plain terms: you may use, study, change, and share Athena, including commercially. If you distribute it, or run a modified version as a service others use over a network, you must make your modified source code available under the same license.

This software is provided **without warranty** of any kind. You are responsible for how you use it and for protecting the information you store in it.
