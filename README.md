# Hospital Management Software

Deployment project for a **10-bed rural hospital in India**: evaluating and standing up an
open-source Hospital Management System (HMS), hosted in the cloud on a tight budget.

## Decisions made so far

| Decision | Choice | Why |
|---|---|---|
| Software | **[GNU Health](https://www.gnuhealth.org)** (Python/Tryton + PostgreSQL) | Actively maintained, Python-native (matches team skills), lower operational complexity than multi-service alternatives (Bahmni), built-in bed/hospitalization management |
| ABDM/ABHA integration | **Not required for now** | Revisit if/when integration with India's Ayushman Bharat Digital Mission becomes necessary (Bahmni would be the better fit if/when this becomes a hard requirement) |
| Hosting | **Cloud**, India region (Mumbai) | Data residency for DPDP Act compliance; low latency from the hospital site |
| Compute | Single VM running Docker Compose (GNU Health/Tryton + self-hosted PostgreSQL + Nginx) | Avoids managed-service costs (RDS, split app/DB servers) that don't make sense at this scale |
| Managed DB service (Supabase etc.) | **Rejected for now** | Free tier lacks backups/SLA and adds cross-network latency + a second vendor for no cost savings once Postgres is self-hosted for free |
| Budget target | **$0–10/month** | Hospital revenue is ~$1000/month; infra cost must stay well under 1-2% of that |

## Next steps, in sequence

### 1. Pick and provision the VM
- [ ] Try **Oracle Cloud "Always Free" tier** first (Mumbai region) — ARM Ampere instance, currently 2 OCPU / 12GB RAM, genuinely free forever. Note: signup approval and regional capacity aren't guaranteed.
- [ ] In parallel, set up a **$6/month DigitalOcean droplet (Bangalore region)** or **AWS Lightsail (Mumbai)** as a cold-standby fallback — don't run it live, just keep the account ready with a recent backup so you can switch within an hour if Oracle has issues.
- [ ] Check whether the hospital qualifies for **nonprofit cloud credits** (AWS via TechSoup, Google for Nonprofits, Microsoft nonprofit program) if it's run by a registered trust/Section 8 company/NGO — could offset costs entirely for 1–2 years.

### 2. Harden the VM
- [ ] Create a non-root sudo user; disable root SSH login.
- [ ] Restrict SSH to your known IP(s) or set up a VPN gate.
- [ ] Set up a firewall (ufw / cloud security group): only 443 (HTTPS) open publicly, SSH locked down.
- [ ] (Optional but recommended) Set up **WireGuard VPN** so staff access the app through the VPN rather than the open internet.
- [ ] Install Docker + Docker Compose.

### 3. Deploy GNU Health
- [ ] Write `docker-compose.yml` with three services: GNU Health/Tryton server, PostgreSQL (with a persistent volume), Nginx reverse proxy.
- [ ] Configure Nginx for TLS via **Let's Encrypt / certbot** (free, auto-renewing).
- [ ] Point a domain name at the VM (~$1/month amortized) for clean HTTPS access.
- [ ] Run `trytond-admin` to initialize the database and install the Hospital/HMIS modules.
- [ ] Create the initial admin user and lock down default credentials.

### 4. Backups (critical — this is the hospital's only copy of patient records)
- [ ] Set up nightly `pg_dump` + WAL archiving.
- [ ] Ship backups to **Backblaze B2** (cheap/free at this data volume) with versioning and a retention policy (e.g. 30 daily + 12 monthly).
- [ ] **Test a restore** — an untested backup isn't a backup.
- [ ] Schedule a recurring quarterly restore-test reminder.

### 5. Connectivity resilience (mitigating the "fully cloud, no local fallback" risk)
- [ ] Set up **dual-WAN failover** at the hospital site (primary broadband + 4G/5G backup router).
- [ ] Put the router/networking gear on a UPS.
- [ ] Write a documented manual/paper fallback procedure for outages.

### 6. Monitoring
- [ ] Set up uptime monitoring (UptimeRobot or similar) against the HTTPS endpoint, with email/SMS alerting.
- [ ] Set up basic log rotation for Docker container logs.

### 7. Data & configuration
- [ ] Configure patient registration to support lookup by **patient ID and phone number**.
- [ ] Set up user roles/permissions for hospital staff (reception, nurses, doctors, pharmacy, admin).
- [ ] Configure the bed/ward module for the 10-bed inpatient setup.
- [ ] Import or set up any existing patient records (if migrating from paper/another system).

### 8. Go-live
- [ ] Train staff on registration, patient lookup, and daily workflows.
- [ ] Run in parallel with any existing paper process for a short trial period.
- [ ] Confirm backup/restore and failover procedures work end-to-end before fully cutting over.

### 9. Revisit later (not needed now)
- [ ] Reassess ABDM/ABHA integration if it becomes a requirement (Bahmni is the stronger candidate for that).
- [ ] Reassess managed database hosting (e.g. Supabase Pro, RDS) if self-hosting becomes an operational burden.
- [ ] Reassess hardware/hosting tier if patient volume grows beyond a single small VM.

## Open questions
- Is the hospital a registered nonprofit/trust (relevant for cloud credit eligibility)?
- Who will own day-to-day operations/maintenance of the server long-term?
