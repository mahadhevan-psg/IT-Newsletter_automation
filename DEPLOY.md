# Deploying to Render (one step)

The whole system - sign-in page, forms page, staff portal, student diary and newsletter studio - runs as **one web service** from one Docker image.

## 1. Put the code on GitHub
Render deploys from a Git repository. Make sure everything is committed and pushed (the new folders `signin/`, `portal/`, `diary/`, `homepage/` and the files `Dockerfile`, `render.yaml`, `docker-entrypoint.sh` must be in the repository).

## 2. Deploy as a Web Service (no Blueprint needed)
Render dashboard -> **New +** -> **Web Service** -> connect your GitHub account and choose the repository, then fill in:

| Field | Value |
|---|---|
| Language | **Docker** (Render finds the `Dockerfile` by itself) |
| Branch | `main` |
| Root Directory | leave empty |
| Instance Type | **Starter** or higher if you want your data kept (see the note below) |

Open **Advanced** and set:

1. **Environment Variables** -> add these two (the rest are already built into the image):

   | Key | Value |
   |---|---|
   | `MASTER_ADMIN_PASSWORD` | a first password of your choice for the `ADMIN` account (you must change it at first sign-in) |
   | `MASTER_SECRET` | any long random text, e.g. 40+ characters (it signs sign-in sessions) |

2. **Health Check Path** -> `/healthz`
3. **Disks** -> **Add Disk**: Name `it-data`, Mount Path **`/data`**, Size 2 GB. (This is what keeps the data. It needs a paid instance type.)

Click **Create Web Service**. The first build takes a few minutes; when it shows **Live**, open the address at the top of the page.

> **Free instance type?** It works, but a free service has **no disk**: the databases are erased every time it restarts or goes to sleep (after ~15 minutes without visits), so it is only good for a demo. For real use choose Starter and add the disk.

### Or: Blueprint (one click, if your account offers it)
**New** -> **Blueprint** -> pick the repository -> **Apply**. [render.yaml](render.yaml) does everything above for you and generates the two secrets (read the password in the service's Environment tab).

## 3. First sign-in
1. Open the service's address (shown at the top of its page, `https://it-department-portal-xxxx.onrender.com`). You land on the sign-in page.
2. The first password is the `MASTER_ADMIN_PASSWORD` you entered (with a Blueprint: service -> **Environment** -> reveal it).
3. Sign in with ID **`ADMIN`** and that password. You are asked to change it straight away.
4. From the portal: **Faculty & roles** (upload faculty), **Classes** (set tutors), then tutors upload their class lists. The guided tour on each page explains the rest.

## Where the data lives
Everything the system changes is on the persistent disk mounted at `/data`, so it survives deploys and restarts:

| What | Where |
|---|---|
| Students, faculty, submissions, placements, logins | `/data/master_system.db` |
| Newsletter entries and issues | `/data/newsletter_system.db` |
| Generated Word files, uploaded photos | `/data/output/` |
| Settings edited in the newsletter studio (forms, sections, layouts, front pages) | `/data/config/` |

Render takes automatic snapshots of the disk (see the service's **Disks** tab) so you can restore an earlier day. Never delete the disk: that deletes the data.

## Settings (environment variables)
Add the two marked below yourself; the others are built into the image (or set by `render.yaml`). Change them under the service's **Environment** tab.

| Variable | Meaning |
|---|---|
| `MASTER_ADMIN_PASSWORD` | Password for the first `ADMIN` account. Only used the first time (when no admin exists yet); after that, change it inside the portal. |
| `MASTER_SECRET` | Key that signs sign-in sessions. Changing it signs everybody out. |
| `MASTER_DB_PATH`, `NEWSLETTER_DB_PATH`, `DATA_DIR` | Where the data lives. Leave as they are. |
| `PORT` | Set by Render. |

## Updating
Push to the connected branch: Render rebuilds and redeploys. The data on the disk is untouched. Studio settings in `/data/config/` are kept as you edited them; to go back to the shipped defaults, delete that one file in the Render **Shell** and restart.

## Run the same image on your own computer
```bash
docker build -t it-portal .
docker run -p 10000:10000 -v it-data:/data -e MASTER_SECRET=change-me -e MASTER_ADMIN_PASSWORD=ChangeMe-123 it-portal
```
Open <http://localhost:10000>. `-v it-data:/data` is the persistent disk; leave it out and the data disappears with the container.

## Good to know
- **One instance only.** The data is SQLite files on one disk, so do not scale to several instances. One is plenty for a department.
- **HTTPS** is provided by Render. A custom domain can be added under **Settings -> Custom Domains**.
- **Health check:** `/healthz` answers `ok` only if both databases can be read; Render uses it to know the service is up.
- **Forgot the only admin password?** Open the service's **Shell** tab and run
  `python -c "from database.master_db import db; from backend.master.auth import hash_password as h; c=db().__enter__(); c.execute(\"UPDATE users SET password_hash=?, must_change=1 WHERE user_id='ADMIN'\", (h('NewTemp-Pass-1'),)); c.commit()"`
  then sign in with `NewTemp-Pass-1` and change it.
