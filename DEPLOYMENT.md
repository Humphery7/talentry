# Deploying Talentry on an Oracle server

This is the "how and why" of getting Talentry running on a fresh Linux server,
from an empty folder to a service that survives crashes and reboots.

It is written so that someone who has never deployed anything can follow it and
understand **why** each command exists, not just what to type.

Server used when this was written: Oracle Cloud, Oracle Linux 9.8, ARM
(`aarch64`), 2 cores, 10 GB RAM.

---

## 0. The mental model (read this first)

Five things will exist when we are done:

| Thing | What it is | Where it listens |
|---|---|---|
| `talentry-backend` | The Node.js API. The website talks to this. | `3001` (behind nginx after part 8) |
| `talentry-career` | The Python service that writes recommendations / interview prep. | `8100`, localhost only |
| `talentry-worker` | The Python background worker that fills out job applications. | no port |
| Neon | The Postgres database. | already online, not on this server |
| systemd | Linux's "service babysitter". Starts programs at boot and restarts them when they die. | — |

Three ideas explain almost every problem you will hit:

1. **A program you start in your terminal dies when you close the terminal.**
   That is why we do not run `npm run dev` on a server. We hand the program to
   systemd instead, and systemd keeps it alive forever.
2. **Linux has more than one firewall.** Oracle Cloud has one at the network
   edge ("Security List"), and the server has its own inside ("firewalld").
   A port must be allowed by **both** before the internet can reach it.
3. **SELinux is a bouncer.** It labels every file and only lets system
   services run files with the right label. Files in your home folder are
   labelled "user data", and system services are not allowed to *execute*
   them. This bites Python virtualenvs, and is explained in part 5.

---

## 1. Logging in (SSH)

SSH is a secure text connection to the server. To use it you need a **key
pair**: a private key (stays on your laptop, never share it) and a public key
(the server already has a copy).

### If you already have the `.key` file Oracle gave you

```bash
mkdir -p ~/.ssh
cp ~/Downloads/ssh-key-DATE.key ~/.ssh/oracle-talentry.key
chmod 600 ~/.ssh/oracle-talentry.key
```

Why `chmod 600`: it means "only my user can read this file". SSH refuses to
use a private key that other users could read, because that would be a security
hole. If you skip this, you get `WARNING: UNPROTECTED PRIVATE KEY FILE`.

Then create a nickname so you never type the IP again. Add this to
`~/.ssh/config`:

```
Host oracle
    HostName 141.144.195.131
    User opc
    IdentityFile ~/.ssh/oracle-talentry.key
```

- `Host oracle` — the nickname. `ssh oracle` now works.
- `User opc` — the account. On Oracle Linux images it is `opc`, on Ubuntu
  images it is `ubuntu`. Using the wrong one gives
  `Permission denied (publickey)`.
- `IdentityFile` — which key to offer.

Test it:

```bash
ssh oracle
```

### If you had no key at all

On a **new** instance, Oracle asks you to upload or generate a key pair while
creating it. If you lost the private key, open the instance's **Console
Connection** in the Oracle console (a serial terminal that needs no key), log in
there, and add a new public key to `~/.ssh/authorized_keys`. You generate the
new pair on your own laptop with:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle-talentry.key
cat ~/.ssh/oracle-talentry.key.pub    # paste this line into authorized_keys
```

---

## 2. Install the two runtimes

A runtime is the program that actually executes your code. This project needs
two: Node.js for the backend, Python for the career service and worker.

### Node.js

Do not install Node with plain `dnf install nodejs` on Oracle Linux — the
version in the system repository is usually too old. NodeSource is the official
third-party repository that carries current versions:

```bash
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo dnf install -y nodejs
node -v      # v22.x
npm -v       # 10.x
```

- `curl ... | sudo bash` downloads a small script that adds the NodeSource
  repository to the machine, then runs it. That is all "installing a repo" is.
- `dnf install nodejs` then installs Node from that repo.
- Node 22 is an LTS ("long term support") release: stable, security-patched,
  supported for years.

The server is ARM (`aarch64`), and NodeSource publishes ARM builds, so this
just works. Your backend has no compiled native modules, so nothing else needs
a compiler.

### Python 3.12

Check what the system has: `python3 --version`. On Oracle Linux 9 it is 3.9,
which is too old — the shared `packages/talentry_embeddings` package requires
3.11 or newer.

```bash
sudo dnf install -y python3.12 python3.12-pip
python3.12 --version
```

We install **3.12 next to 3.9**, we do not remove 3.9. The operating system
itself uses 3.9 for its own tools; replacing it is how you break a server.

---

## 3. Clone the code

```bash
cd ~
git clone https://github.com/Humphery7/talentry.git talentry
cd talentry
```

Why clone the whole repo when only two of its five folders run here: the
folders share one history, one `git pull`, and one set of docs. A partial
checkout would save a few megabytes and cost you an hour every time you update.

The repo is public, so no token or password is needed. (If it were private, you
would use a GitHub personal access token or a deploy key.)

Nothing here touches `Chronicle-Application`; it just lives beside it in
`/home/opc`.

---

## 4. The backend (Node)

```bash
cd ~/talentry/talentry-backend
npm ci
npm run build
```

### What those two commands did

- **`npm ci`** installs exactly the dependency versions pinned in
  `package-lock.json`. Use it on servers instead of `npm install`: `install`
  may quietly upgrade things, `ci` is reproducible and wipes `node_modules`
  first so you never get half-updated state.
- **`npm run build`** runs `tsc` (the TypeScript compiler). The source is
  `.ts`; Node cannot run that directly. The compiler writes plain `.js` into
  `dist/`. In production we run `node dist/server.js`, which is why the server
  needs no compiler and no `tsx`.
- Any later code change therefore needs a rebuild. Otherwise you restart the
  service and it keeps running the old compiled code.

### The `.env` file

The app reads its settings and secrets from `.env` in the same folder. It is
never committed (it is in `.gitignore`), and the file already exists on your
laptop, so copy it up instead of retyping secrets:

```bash
# run this on your own machine, not on the server
scp ~/talentry/talentry-backend/.env oracle:~/talentry/talentry-backend/.env
```

Then lock it down on the server:

```bash
chmod 600 ~/talentry/talentry-backend/.env
```

What the important values mean:

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Neon connection string. Same database the crawler fills. |
| `PORT` | `3001` — the port the API listens on. |
| `JWT_SECRET` | Signs login tokens. Changing it logs everyone out. |
| `SESSION_SECRET` | Signs the short-lived Google-login cookie. |
| `AI_KEY_SECRET` | Encrypts each user's own Gemini key. **Must be identical in `talentry-career/.env`.** |
| `CAREER_API_URL` | `http://localhost:8100` — where the backend finds the career service. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google sign-in credentials. |
| `REDIRECT_URL` | Must match the redirect URL registered in Google's console. |
| `FRONTEND_URL` | Where the browser is sent after login. |

### Try it by hand first

```bash
node dist/server.js
```

You should see `Talentry API listening on http://localhost:3001`. Press
**Ctrl+C**.

Always run a service by hand once before giving it to systemd. If it cannot
start manually, systemd will only hide the error in a log file and restart it
in a loop.

### Hand it to systemd

Create `/etc/systemd/system/talentry-api.service`:

```bash
sudo tee /etc/systemd/system/talentry-api.service > /dev/null <<'EOF'
[Unit]
Description=Talentry API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/talentry/talentry-backend
ExecStart=/usr/bin/node dist/server.js
Environment=NODE_ENV=production
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Line by line:

| Line | Why |
|---|---|
| `After=network-online.target` | Do not start before the network is up; the app needs the database. |
| `Type=simple` | "The program I start stays in the foreground." Correct for both Node and uvicorn. |
| `User=opc` | Never run app code as root. If the app is compromised, the damage stays small. |
| `WorkingDirectory` | Where the process starts. `.env` and `dist/` are found relative to it. |
| `ExecStart` | The exact program and arguments. Use a full path — systemd has a minimal `PATH`. |
| `Environment=NODE_ENV=production` | Tells libraries to behave like production (no dev extras). |
| `Restart=always` | Restart on crash **and** on clean exit. This is the "comes back by itself" you asked for. |
| `RestartSec=5` | Wait 5 seconds between attempts, so a broken app cannot spin at 100% CPU. |
| `WantedBy=multi-user.target` | Makes `systemctl enable` actually start it at boot. |

Why there is no `EnvironmentFile=` line: the app loads `.env` itself with the
`dotenv` package. One source of truth beats two that can disagree.

Then:

```bash
sudo systemctl daemon-reload          # reread unit files after editing them
sudo systemctl enable --now talentry-api
systemctl status talentry-api --no-pager
```

- `daemon-reload` is required after **any** change to a `.service` file.
- `enable` = start at boot. `start` = start right now. `enable --now` does both.
- `status` shows the state, the last log lines, and (most usefully) the exact
  command it tried to run.

Check it answers:

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:3001/
```

`200` means the API is alive.

---

## 5. The career service (Python)

```bash
cd ~/talentry/talentry-career
python3.12 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

- A **virtualenv** (`.venv`) is a private folder of Python packages for this
  project. It keeps Talentry's versions away from the system Python, so
  installing one project can never break another.
- `python3.12 -m venv .venv` builds that folder with Python 3.12.
- `.venv/bin/pip` is the pip that lives *inside* the venv. So
  `.venv/bin/pip install` installs into the venv, while a bare `pip install`
  would install system-wide.
- `requirements.txt` pins exact versions, like `package-lock.json` does for
  Node. One of its lines is `-e ../packages/talentry_embeddings`, which
  installs the shared embeddings package from this same repo ("editable", so a
  `git pull` updates it without reinstalling).

Copy its env file the same way:

```bash
# on your machine
scp ~/talentry/talentry-career/.env oracle:~/talentry/talentry-career/.env
```

```bash
# on the server
chmod 600 ~/talentry/talentry-career/.env
```

It holds `DATABASE_URL`, `GEMINI_API_KEY`, `PLAYWRIGHT_CHANNEL`, and
`AI_KEY_SECRET` (must equal the backend's value). Keep `PLAYWRIGHT_CHANNEL`
empty on the server — see the browser section below.

Test by hand:

```bash
.venv/bin/uvicorn app:app --app-dir src --port 8100
```

`uvicorn` is the web server that runs the FastAPI app. `app:app` means "the
object named `app` inside `app.py`". `--app-dir src` tells it where to look.

### The systemd unit — and the SELinux trap

```bash
sudo tee /etc/systemd/system/talentry-career.service > /dev/null <<'EOF'
[Unit]
Description=Talentry Career API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/talentry/talentry-career
Environment=PYTHONPATH=/home/opc/talentry/talentry-career/src
Environment=PYTHONUNBUFFERED=1
# The worker has its own unit below; do not also start a copy inside this one.
Environment=AGENT_WORKER_ENABLED=0
ExecStart=/home/opc/talentry/talentry-career/.venv/bin/uvicorn app:app --app-dir src --host 127.0.0.1 --port 8100
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

- `--host 127.0.0.1` keeps this service **internal**. Only programs on the
  same machine can reach it (our backend). The internet never sees port 8100.
- `PYTHONPATH` lets the code import from `src/`.
- `PYTHONUNBUFFERED=1` makes logs appear immediately instead of sitting in a
  buffer.
- `AGENT_WORKER_ENABLED=0` is easy to miss and worth understanding. The career
  app has a supervisor that starts the auto-apply worker as a **child process**
  when it boots, so a deployment that only runs the FastAPI app still works.
  We give the worker its own service (part 6), so without this line the worker
  runs **twice**: once from systemd, once as a child of this service. It is not
  catastrophic — the queue is claimed with `FOR UPDATE SKIP LOCKED`, so the two
  copies will not pick the same job — but it doubles the polling, doubles the
  memory, and makes logs confusing. `AGENT_WORKER_ENABLED=0` turns the built-in
  supervisor off. (`npm run dev` sets the same variable, for the same reason.)

The first start failed with:

```
status=203/EXEC
Failed to locate executable ... Permission denied
```

`203/EXEC` means systemd could not **execute** the program. The file existed,
the paths were right, and running it by hand as `opc` worked. The difference is
**SELinux**:

```bash
ls -Z /home/opc/talentry/talentry-career/.venv/bin/uvicorn   # ...:user_home_t:s0
ls -Z /usr/bin/node                                          # ...:bin_t:s0
```

`user_home_t` is the label for personal files; system services may read them but
not run them. `/usr/bin/node` is `bin_t` ("binary"), which is allowed. That is
why the Node service worked and the Python one did not.

The fix is to relabel just the venv's `bin` folder as executable code:

```bash
sudo dnf install -y policycoreutils-python-utils   # provides `semanage`
sudo semanage fcontext -a -t bin_t "/home/opc/talentry/talentry-career/.venv/bin(/.*)?"
sudo restorecon -Rv /home/opc/talentry/talentry-career/.venv/bin
```

- `semanage fcontext` writes a **rule** ("files matching this path get this
  label"), and it survives reboots.
- `restorecon` actually applies the rule to the files that already exist.
- If you ever re-run `semanage fcontext -a` for the same path it errors with
  "already defined"; use `-m` (modify) instead of `-a` (add).

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now talentry-career
curl -s -o /dev/null -w '%{http_code}\n' localhost:8100/health
```

Right after a restart, `curl` may return `000` for a second or two — that just
means "connection refused because the app is still booting". Retry before
assuming it is broken.

---

## 6. The agent worker

`npm run dev` starts four things; one of them is a Python worker that drives a
real browser to fill in job applications. It has no web port: it polls the
database for work. That is why it is a separate service — if it crashes it must
not take the API down with it.

The worker must run in **exactly one place**. The career app can start one by
itself (part 5 explains `AGENT_WORKER_ENABLED=0`), and this unit starts another.
Keep the line in part 5, and the only copy will be this service.

It needs Chromium. Playwright downloads its own copy, and we deliberately put
it in `/opt` instead of the home folder, for the same SELinux reason as above:

```bash
sudo mkdir -p /opt/talentry-browsers
sudo chown opc:opc /opt/talentry-browsers
cd ~/talentry/talentry-career
PLAYWRIGHT_BROWSERS_PATH=/opt/talentry-browsers .venv/bin/playwright install chromium
```

`PLAYWRIGHT_BROWSERS_PATH` is the environment variable that tells Playwright
where to keep browsers. It must be set **both** when installing and when
running.

Chromium also needs a few system libraries on a minimal Oracle Linux image:

```bash
sudo dnf install -y alsa-lib atk at-spi2-core mesa-libgbm \
  libXcomposite libXdamage libXfixes libxkbcommon libXrandr
```

Leave `PLAYWRIGHT_CHANNEL` empty in `talentry-career/.env`. Setting it to
`chrome` makes Playwright look for Google Chrome, which has no Linux arm64
build and is not installed on the server; every apply then fails with
`Chromium distribution 'chrome' is not found`.

### LibreOffice (reusing the candidate's own CV layout)

When a candidate uploads a DOCX, the worker edits that file and converts it
back to PDF with LibreOffice. Without it the application still runs, but the
CV falls back to the standard layout:

```bash
sudo dnf install -y libreoffice-writer
soffice --version
```

```bash
sudo tee /etc/systemd/system/talentry-worker.service > /dev/null <<'EOF'
[Unit]
Description=Talentry agent worker
After=network-online.target talentry-career.service
Wants=network-online.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/talentry/talentry-career
Environment=PYTHONPATH=/home/opc/talentry/talentry-career/src
Environment=PYTHONUNBUFFERED=1
Environment=PLAYWRIGHT_BROWSERS_PATH=/opt/talentry-browsers
ExecStart=/home/opc/talentry/talentry-career/.venv/bin/python -m services.agent_applications.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now talentry-worker
```

The worker prints nothing while idle — that is normal. Confirm it is really
alive and not crash-looping:

```bash
systemctl is-active talentry-worker
systemctl show -p NRestarts --value talentry-worker   # 0 means it never crashed
```

---

## 7. Opening the door (two firewalls)

Only the backend needs to be public. The career service and worker stay
internal. Part 8 puts nginx in front of it, and at that point the public door
becomes `443` instead of `3001`.

**Layer 1, inside the server** (`firewalld`):

```bash
sudo firewall-cmd --permanent --add-port=3001/tcp
sudo firewall-cmd --reload
```

`--permanent` saves the rule for reboots; `--reload` applies it now. Without
the reload the rule exists but does nothing. Check with
`sudo firewall-cmd --list-ports`.

**Layer 2, at Oracle Cloud** (in the web console, not SSH):

Networking → Virtual Cloud Networks → your VCN → Security Lists →
*Default Security List* → **Add Ingress Rule**

- Source CIDR: `0.0.0.0/0` (anywhere)
- Protocol: `TCP`
- Destination Port: `3001`

Neither layer knows about the other. That is why a port can look "open" and
still be unreachable.

Test from your laptop (not the server — the server would talk to itself and
always succeed):

```bash
curl -m 10 -s -o /dev/null -w '%{http_code}\n' http://141.144.195.131:3001/
```

`200` = the world can reach it. `000` = one of the two layers still blocks it,
or the app is not listening.

---

## 8. HTTPS (nginx + a free certificate)

### 8.1 Why the API needs HTTPS at all

Picture the finished setup: the website is on `https://something.vercel.app`,
and the API is on `http://141.144.195.131:3001`. One is encrypted, the other is
not. The browser refuses to let the first talk to the second, and the message
it prints is:

```
Mixed Content: The page at 'https://something.vercel.app/...' was loaded over
HTTPS, but requested an insecure resource
'http://141.144.195.131:3001/api/auth/login'. This request has been blocked.
This content must be served over HTTPS.
```

In the Network tab the request shows `(blocked:mixed-content)` with status `0`.
Note what that means for debugging: **the request never leaves the browser.**
Your server logs stay empty, `curl` from your laptop works, and it looks like
the API is down when it is perfectly healthy. If you ever see "it works in
curl but not in the browser", this is the first thing to check.

**What "mixed content" is.** Every page has an origin: scheme (`http`/`https`),
host, and port. A page loaded over HTTPS is a *secure origin*. A page may not
pull *active* resources from an insecure origin. The reason is the promise the
padlock makes: "nobody altered this page in transit". If an HTTPS page were
allowed to quietly fetch over HTTP, anyone on the network path (a café Wi-Fi,
a hosting provider, a compromised router) could swap the response and inject
JavaScript into an otherwise trusted page. The padlock would be a lie, so the
browser enforces the rule for you.

The rule is applied in two strengths:

| Kind | Examples | What the browser does |
|---|---|---|
| **Passive** | images, audio, video | Tries to upgrade the URL to `https://`; if that fails, blocks it |
| **Active** | `fetch`/XHR, scripts, iframes, CSS, form posts | Blocks immediately, always |

Every API call — login, saved jobs, apply — is a `fetch()`. That is active
content, so it is always blocked. There is no partial mode.

**You cannot switch it off.** Chrome used to offer a shield icon to "load unsafe
scripts"; it was removed in 2015 (Chrome 46). What remains is an enterprise
policy and a command-line flag, neither of which a normal visitor will use.
Firefox and Safari behave the same way. So when you see this error, the browser
is not misconfigured — the deployment is.

### 8.2 What this means for *this* frontend (the accurate version)

It is tempting to say "the whole site breaks". That is not quite true, and the
difference matters when you are debugging. This frontend talks to the backend
in two different ways.

**Path A — server-side, used by most of the app.** The files under
`talentry-frontend/app/api/**/route.ts` do not run in the browser. They run on
Vercel's servers. They read `API_URL` and call the backend from Node, then hand
the result back to the browser. The browser only ever sees a same-origin
request to `https://<your-vercel-domain>/api/...`, which is HTTPS. Mixed content
never enters the picture, because the browser is not the one making the HTTP
call.

**Path B — client-side, used in a few places.** `NEXT_PUBLIC_API_URL` is
compiled into the JavaScript bundle, so the *browser* makes that request. In
this repo it appears in exactly three places:

- `app/(app)/saved/page.tsx` — loading the saved-jobs list
- `components/landing/AuthModal.tsx` — login, signup, and the Google button
- `components/ApplyButton.tsx` — the apply action

If `NEXT_PUBLIC_API_URL` is left **empty**, those three calls go to the same
origin and are proxied by Path A, so they work. If it is set to
`http://141.144.195.131:3001`, exactly those three features break while the rest
of the site keeps working — which is the most confusing failure mode there is.
So: leave it empty, or point it at `https://`, never at `http://`.

**Path A is not blocked, but it is not safe either.** Vercel's server calling
`http://141.144.195.131:3001` crosses the public internet in plaintext. Every
login POST with a password, every `Authorization: Bearer <jwt>` header, every
Google token is readable by anyone who can observe that path. HTTPS is not just
a browser rule; it is the only thing preventing credential theft on a shared
network. The blocked fetch is the loud problem. The plaintext credentials are
the quiet one, and they are the more serious of the two.

### 8.3 The two legitimate fixes

1. **Give the API a certificate** (what we do in this part). nginx listens on
   `443`, decrypts, and forwards plain HTTP to `127.0.0.1:3001`. Plaintext over
   loopback never leaves the machine, so that leg is fine.
2. **Make the API same-origin with the frontend** — send every browser call to
   `/api/...` on the frontend domain and let Next.js proxy it server-side. This
   avoids mixed content with no certificate, but every byte then flows through
   Vercel's functions (extra latency and invocation cost), and the server-to-
   server leg is still plaintext unless the target is HTTPS. You end up doing
   fix 1 anyway.

Not fixes, even though they look like ones: disabling the browser check,
setting `NEXT_PUBLIC_API_URL` to the HTTP API "just for now", or wrapping the
API in an iframe. All three either fail for real users or leave credentials
exposed.

### 8.4 How HTTPS actually works, in one page

Three things have to be true at once: **encryption**, **identity**, **trust**.

- **Encryption** — TLS wraps the connection. The two sides agree on a session
  key, and everything after that is scrambled. Someone watching the packets
  sees ciphertext.
- **Identity** — the server presents a *certificate*: "this public key belongs
  to `141-144-195-131.sslip.io`, and Let's Encrypt vouches for it".
- **Trust** — your browser and operating system ship with a list of Certificate
  Authorities (CAs) they trust. If the certificate's signature chains back to
  one of them, the name in the certificate matches the name in the URL, and the
  dates are valid, you get the padlock. If any check fails you get an error such
  as `NET::ERR_CERT_AUTHORITY_INVALID` (unknown signer) or
  `ERR_CERT_COMMON_NAME_INVALID` (wrong name). Those errors are the browser
  telling you which of the three checks failed.

The handshake, simplified:

1. Browser: "hello, I want to talk to `141-144-195-131.sslip.io`."
2. Server: sends its certificate.
3. Browser: verifies the signature against its trusted CA list, the name
   against the URL, and the expiry dates.
4. Both sides derive a shared session key; the server proves it holds the
   certificate's private key.
5. Everything after this point is encrypted with that session key.

**Why a name is needed.** Certificates are issued for *names*, not addresses.
Let's Encrypt will not issue one for a bare IP, and the browser compares the
name in the URL to the name in the certificate. That is the entire reason
`sslip.io` appears in this setup: it is a free public DNS service that turns
`141-144-195-131.sslip.io` into `141.144.195.131`, so there is a name to
certify. You do not own it, and you can swap in a real domain later by pointing
an `A` record at the server and repeating the same certbot command with the new
name.

**How Let's Encrypt knows the server is yours.** It uses a protocol called
ACME. certbot asks for a certificate; Let's Encrypt replies "serve this random
token at `http://<name>/.well-known/acme-challenge/<token>`". Let's Encrypt then
fetches that URL from the public internet. If the token matches, you control
the name, and the certificate is issued. This is exactly why port `80` must be
open at **both** firewalls before you run certbot: if the check cannot reach
you, you get a validation error instead of a certificate. It is also why nginx
must already be answering on port 80 — the token is served by nginx, not by
your Node app.

**Why 90 days, and why renewal matters.** Short lifetimes limit the damage if a
private key ever leaks, and they force automation instead of one-time manual
setup. Renewal is the same ACME exchange, run by a timer. If that timer is
disabled — which is the default for the EPEL package here — the certificate
expires silently and every visitor gets a full-page security warning. That is
why we enable the timer *and* run `--dry-run`: it proves renewal works now,
instead of finding out in 89 days.

**Why nginx and not the Node app.** TLS is a solved, boring problem and nginx
is very good at it. Keeping certificates out of the application means the app
keeps speaking plain HTTP on `127.0.0.1`, restarting the API never drops TLS,
and one nginx can front several services later. The app never learns that
certificates exist.

The pattern is therefore always the same: **nginx** sits on ports 80/443,
terminates HTTPS, and forwards the request to the app on `127.0.0.1:3001`.

### 8.5 Install the packages

```bash
sudo dnf install -y nginx
```

`certbot` (the program that gets certificates from Let's Encrypt) is not in
Oracle's normal repositories, it comes from EPEL, which is installed but
**disabled** on this image:

```bash
sudo dnf config-manager --enable ol9_developer_EPEL
sudo dnf --refresh install -y certbot python3-certbot-nginx
```

*(No domain? `sslip.io` is a free public service that answers any name shaped
like an IP: `141-144-195-131.sslip.io` → `141.144.195.131`. You do not own it,
but it works for a certificate. Swap in your own domain later and repeat the
same steps.)*

### 8.6 The nginx site

Create `/etc/nginx/conf.d/talentry.conf`:

```bash
sudo tee /etc/nginx/conf.d/talentry.conf > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name 141-144-195-131.sslip.io;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF
```

| Line | Why |
|---|---|
| `listen 80` / `[::]:80` | IPv4 and IPv6. certbot needs port 80 to prove you own the name. |
| `server_name` | Which hostname this block answers to. Other hostnames get the default. |
| `client_max_body_size 20m` | CV uploads. nginx's default is 1 MB and would reject them with `413`. |
| `proxy_pass` | Where to forward. `127.0.0.1` means "this same machine". |
| `proxy_set_header Host` | Keeps the real hostname, so links the app builds are correct. |
| `X-Real-IP` / `X-Forwarded-For` | The app would otherwise see every visitor as `127.0.0.1`. |
| `X-Forwarded-Proto` | Tells the app the visitor used HTTPS, so it makes HTTPS links. |
| `proxy_read_timeout 120s` | Some AI/recommendation calls take a while. The default 60 s can cut them off. |

One more SELinux switch, same family of problem as part 5:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

By default SELinux does not let the web server open outbound connections.
Without this, nginx starts fine and every request returns **502 Bad Gateway**.
`-P` makes it permanent across reboots.

Then open the ports and start it:

```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --reload
sudo nginx -t                # checks the config; always do this before restarting
sudo systemctl enable --now nginx
```

and in the Oracle console, add **two more ingress rules**: TCP `80` and TCP
`443`, source `0.0.0.0/0`.

Test locally first (the server talking to itself), faking the hostname:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Host: 141-144-195-131.sslip.io" http://127.0.0.1/
```

`200` means nginx reached the API. `502` means nginx is up but could not reach
`3001` (check `systemctl status talentry-api` and the SELinux boolean above).

### 8.7 Get the certificate

From your laptop, confirm port 80 is reachable before asking for a cert:

```bash
curl -m 10 -s -o /dev/null -w '%{http_code}\n' http://141-144-195-131.sslip.io/
```

Then:

```bash
sudo certbot --nginx -d 141-144-195-131.sslip.io \
  --agree-tos --register-unsafely-without-email --redirect --non-interactive
```

- `--nginx` lets certbot edit the nginx block itself and add the `443` server.
- `--redirect` makes port 80 forward to `https://` instead of serving the API
  unencrypted.
- `--register-unsafely-without-email` skips the account email. You can add one
  later with `sudo certbot update_account --email you@example.com` (useful, so
  Let's Encrypt can warn you before a certificate expires).

### 8.8 Make renewal automatic

Certificates last 90 days. The EPEL package ships a renewal timer but leaves it
**disabled**, which is a silent trap:

```bash
sudo systemctl enable --now certbot-renew.timer
systemctl list-timers certbot-renew.timer --no-pager
sudo certbot renew --dry-run      # proves renewal will work, without spending a real attempt
```

`--dry-run` matters: if the certificate cannot be renewed, you find out now
instead of in 89 days at 3 a.m.

Verify from your laptop:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://141-144-195-131.sslip.io/
```

`200` over HTTPS means you are done.

Once HTTPS works you can close port `3001` to the internet and leave only
80/443 open, so every request passes through nginx:

```bash
sudo firewall-cmd --permanent --remove-port=3001/tcp
sudo firewall-cmd --reload
```

(Also delete the `3001` ingress rule in the Oracle console.)

---

## 9. The reboot test

The point of systemd is surviving a reboot. Prove it:

```bash
sudo reboot
```

Wait ~40 seconds, log back in, then:

```bash
uptime -p
for s in talentry-api talentry-career talentry-worker; do
  printf "%-18s %s (boot: %s)\n" "$s" "$(systemctl is-active $s)" "$(systemctl is-enabled $s)"
done
curl -s -o /dev/null -w '%{http_code}\n' localhost:3001/
```

All three should be `active` and `enabled`, with no manual help.

---

## 10. Day-2 operations

```bash
# what is running
systemctl status talentry-api talentry-career talentry-worker --no-pager

# live logs (Ctrl+C to stop watching)
sudo journalctl -u talentry-api -f
sudo journalctl -u talentry-career -f
sudo journalctl -u talentry-worker -f

# last 50 lines, no follow
sudo journalctl -u talentry-api -n 50 --no-pager

# restart / stop / start one service
sudo systemctl restart talentry-api
sudo systemctl stop talentry-api
sudo systemctl start talentry-api

# disk space (a full disk breaks everything)
df -h /
```

### Deploying new code

```bash
cd ~/talentry
git pull

cd talentry-backend
npm ci
npm run build
sudo systemctl restart talentry-api

# only if talentry-career/requirements.txt changed
cd ../talentry-career
.venv/bin/pip install -r requirements.txt
sudo systemctl restart talentry-career talentry-worker
```

`git pull` alone changes nothing that is running: the API runs compiled files
in `dist/`, and the services keep the version they started with. Restarting is
what makes the new code live.

---

## 11. Troubleshooting

| Symptom | Meaning | Fix |
|---|---|---|
| `203/EXEC` | systemd cannot execute the program | Check the path in `ExecStart`; on this box almost always the SELinux label (part 5). |
| `203/EXEC` with `Permission denied` | Same, SELinux | `ls -Z` the file; relabel with `semanage` + `restorecon`. |
| `000` from `curl` | Connection refused | Service not running, wrong port, or still booting. Check `systemctl status` and the logs. |
| `000` from your laptop, `200` from the server | Firewall | Open the port in **both** layers (part 7). |
| `Permission denied (publickey)` | Wrong user or wrong key | `opc` for Oracle Linux, `ubuntu` for Ubuntu; check `IdentityFile`. |
| `UNPROTECTED PRIVATE KEY FILE` | Key readable by others | `chmod 600` the key. |
| `EADDRINUSE` | Port already taken | `ss -tlnp \| grep 3001` to see who owns it. |
| `Cannot find module dist/server.js` | Forgot to build | `npm run build`. |
| `DATABASE_URL is not set` | `.env` missing or in the wrong folder | It must sit beside `package.json` / `pyproject`; check `WorkingDirectory`. |
| pg warns about `sslmode=require` | Future `pg` version will verify certificates | Harmless today; can silence with `uselibpqcompat=true` appended to `DATABASE_URL`. |
| Service restarts every 5 seconds | It is crash-looping | `journalctl -u <service> -n 50` shows the real error. |
| Browser console: `Mixed Content ... has been blocked`, Network shows `(blocked:mixed-content)` and status `0` | An `https://` page tried to call an `http://` URL. The request never left the browser, so the server logs nothing. | Use the `https://` API URL, or leave `NEXT_PUBLIC_API_URL` empty so Next.js proxies server-side (part 8.1–8.2). |
| `502 Bad Gateway` from nginx, but `curl localhost:3001` works on the server | SELinux is stopping nginx from making outbound connections | `sudo setsebool -P httpd_can_network_connect 1` (part 8). |
| `413 Request Entity Too Large` on upload | nginx's 1 MB default body limit | `client_max_body_size 20m;` in the `server` block (part 8). |
| `NET::ERR_CERT_AUTHORITY_INVALID` / `ERR_CERT_COMMON_NAME_INVALID` | Certificate unknown, or issued for a different name | Check `sudo certbot certificates`; the name in the URL must match `server_name`. |
| Certificate expired, every visitor sees a warning page | Renewal timer never ran | `sudo systemctl enable --now certbot-renew.timer`; then `sudo certbot renew --dry-run` (part 8). |

---

## 12. What this setup does NOT do yet

1. **Frontend deployment.** `talentry-frontend` is not on this server. If it is
   on Vercel, set these in the Vercel project settings — not in this repo:
   - `API_URL=https://141-144-195-131.sslip.io` (used by the server-side
     `app/api/**/route.ts` proxies; never add `:3001`, never use `http://`)
   - `NEXT_PUBLIC_API_URL` — **leave it empty** unless you have a reason not
     to. Empty means the three client-side callers (saved jobs, `AuthModal`,
     `ApplyButton`) use the same-origin Next.js proxy, which cannot hit mixed
     content. If you do set it, it must be `https://` (part 8.2).
2. **Google OAuth for the new address.** Three values have to agree, and they
   live in three different places:

   | Value | Where | Must be |
   |---|---|---|
   | Authorized redirect URI | Google Cloud Console → Credentials → your OAuth client | `https://141-144-195-131.sslip.io/auth/google/callback` |
   | `REDIRECT_URL` | backend `.env` | the same URL, exactly |
   | `FRONTEND_URL` | backend `.env` | your Vercel origin, e.g. `https://talentry-virid.vercel.app` (no trailing slash) |

   `REDIRECT_URL` is where Google sends the browser back (this API).
   `FRONTEND_URL` is where the API sends it next, with the login token. If
   `FRONTEND_URL` still says `http://localhost:3000`, login "succeeds" and then
   dumps the user on a dead page.

   After editing `.env`, `sudo systemctl restart talentry-api`. Then check the
   handshake without a browser:

   ```bash
   curl -s -D - -o /dev/null https://141-144-195-131.sslip.io/auth/google/login \
     | grep -iE '^(location|set-cookie)'
   ```

   The `location` must contain your `redirect_uri` and there must be a
   `Set-Cookie: connect.sid=...; Secure`. No cookie means the Google callback
   will answer `400 Login session expired` — that is the `trust proxy` setting
   in `talentry-backend/src/app.ts`, which must stay in place because nginx is
   the one doing HTTPS.

   **"Authorized JavaScript origins" can stay `http://localhost:3000`.** That
   field is only used by Google's browser-side JavaScript SDK. This app never
   loads it: the Google button is a full-page redirect to
   `/auth/google/login`. Only the **redirect URI** list matters here. Adding
   `https://talentry-virid.vercel.app` to the JS origins is harmless, just not
   required.
3. **A domain you own.** `sslip.io` is fine for testing but it is not yours.
   When you buy one, point an `A` record at `141.144.195.131`, change
   `server_name` in `/etc/nginx/conf.d/talentry.conf`, and run certbot again
   with the new name.

---

## Appendix: the values used here

| Item | Value |
|---|---|
| Server IP | `141.144.195.131` |
| SSH user | `opc` |
| Code | `/home/opc/talentry` |
| Backend | `/home/opc/talentry/talentry-backend` |
| Career | `/home/opc/talentry/talentry-career` |
| Python | `/home/opc/talentry/talentry-career/.venv/bin/python` |
| Services | `talentry-api`, `talentry-career`, `talentry-worker` |
| Unit files | `/etc/systemd/system/talentry-*.service` |
| Playwright browsers | `/opt/talentry-browsers` |
| Public URL | `https://141-144-195-131.sslip.io` |
| nginx site | `/etc/nginx/conf.d/talentry.conf` |
| Certificate | `/etc/letsencrypt/live/141-144-195-131.sslip.io/` |
| API port | `3001` (internal once nginx is in front) |
| Career port | `8100` (internal) |
