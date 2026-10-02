# Getting your GHL Firebase refresh token

You only need this if you want to **build/update workflows** (the internal-API
`--experimental` commands). Everything else works with just `GHL_API_KEY`.

Contract-template authoring also needs a current `GHL_IAM_TOKEN`; see the
separate section below.

The token is read from your own logged-in GoHighLevel session — no extension, no
install, nothing leaves your browser. You paste a one-line snippet into the browser's
DevTools console and it copies the token to your clipboard.

## Steps

1. In Chrome (or any Chromium browser), open and log into `https://app.gohighlevel.com`.
2. Open DevTools: **⌘⌥J** (Mac) / **Ctrl-Shift-J** (Windows/Linux) to jump straight to the
   Console.
3. Paste this and press Enter:

   ```js
   (async () => {
     const db = await new Promise((res, rej) => {
       const r = indexedDB.open("firebaseLocalStorageDb");
       r.onsuccess = e => res(e.target.result);
       r.onerror = () => rej("Cannot open IndexedDB");
     });
     const entries = await new Promise((res, rej) => {
       const tx = db.transaction("firebaseLocalStorage", "readonly");
       const all = tx.objectStore("firebaseLocalStorage").getAll();
       all.onsuccess = () => res(all.result);
       all.onerror = () => rej("Failed to read store");
     });
     for (const e of entries) {
       const v = e?.value || e;
       const stm = v?.stsTokenManager;
       if (stm?.refreshToken) {
         // The web key is on the record itself, or embedded in its IndexedDB
         // key as firebase:authUser:<apiKey>:[DEFAULT].
         const apiKey = v?.apiKey || String(e?.fbase_key || "").split(":")[2] || "";
         const env =
           `GHL_FIREBASE_REFRESH_TOKEN=${stm.refreshToken}\n` +
           `GHL_FIREBASE_API_KEY=${apiKey}`;
         copy(env); // DevTools copy() helper → clipboard
         console.log("✓ Both values copied. Paste them into .env as-is.");
         if (!apiKey) console.warn("Web key not found — copy it from any app.gohighlevel.com network request's ?key= parameter.");
         return;
       }
     }
     console.warn("No refresh token found — make sure you're logged into GHL on this tab.");
   })();
   ```

4. The console prints `✓ Both values copied.` — two ready-made `.env` lines are now on
   your clipboard.
5. Paste them into your `.env`:

   ```env
   GHL_FIREBASE_REFRESH_TOKEN=<pasted>
   GHL_FIREBASE_API_KEY=<pasted>
   ```

   Both are read from your own session. Neither is vendored in this package, so an
   `--experimental` command will stop with a clear message until both are set.

> If the console shows `No refresh token found`, make sure you ran the snippet on an
> `app.gohighlevel.com` tab where you're logged in (not a marketing page).

## Contract templates: you almost certainly do not need this

**Contract-template authoring works on the Firebase session alone.** The
proposal service was measured on 2026-08-24: a template GET with `token-id` and
no `Authorization` header returns 200 and the full template. Leave
`GHL_IAM_TOKEN` unset and skip this section.

It is documented only because the template builder *does* send an IAM bearer
alongside `token-id`, so a network capture makes it look mandatory. It is not.
And if a contract command 401s while `GHL_IAM_TOKEN` is set, the fix is to
**unset it**, not to copy a fresh one: the service resolves a bearer whenever it
receives one, so a stale value fails where an empty one succeeds.

If you have a specific reason to send it anyway, copy it without hunting through
request headers:

1. In your logged-in GHL account, open Payments, then Documents & Contracts,
   Templates, and open any template in the editor.
2. Open DevTools, select the Console, then use the execution-context selector
   at the top of the Console to choose the proposal-builder frame.
3. Paste this and press Enter:

   ```js
   (() => {
     const token = window.getAuthToken?.();
     if (!token) {
       console.warn("IAM token unavailable — select the proposal-builder frame and retry.");
       return;
     }
     copy(`GHL_IAM_TOKEN=${String(token).replace(/^Bearer\s+/i, "")}`);
     console.log("✓ GHL_IAM_TOKEN copied. Paste it into .env as-is.");
   })();
   ```

4. Paste the copied line into the profile the `ghl` wrapper actually loads:

   ```env
   # ~/.config/ghl/profiles/<profile>.env
   GHL_IAM_TOKEN=<copied token without the Bearer prefix>
   ```

   Not the `.env` beside this skill. The wrapper resolves a profile — `GHL_PROFILE`,
   else a `.ghlprofile` file walking up from the working directory, else
   `default_profile` in `~/.config/ghl/config` — and loads
   `~/.config/ghl/profiles/<profile>.env`. A token in the skill folder's `.env` is
   never read, and the command that needs it still reports the credential missing.

IAM tokens are short lived. Copy a fresh one when a template command reports
an authorization failure. The CLI does not store or refresh this independent
credential. Do not substitute `GHL_FIREBASE_TOKEN`; the proposal service checks
both credentials.

## Security — read before you use this

- **This token is your entire GHL login**, not a scoped key. It grants full account
  access — anyone who obtains it can do anything you can. (The scoped, revocable
  Private Integration Token in `GHL_API_KEY` is the safe default for everything else.)
- **Own-account-only.** Generate and use this token only on **your own** agency
  account. **Never** paste a *client's* token, and never run the internal API against
  client sub-accounts. To provision workflows for clients, build the workflow once in
  the GHL UI and ship it in a **Snapshot** — sub-accounts inherit it on provision, with
  no token and no internal API. See the "Workflow building" section of the README.
- **Treat it like a password.** `.env` is gitignored — never commit it — and prefer
  sourcing the token from a secret manager / OS keychain rather than leaving it at rest
  in `.env`.
- Treat `GHL_IAM_TOKEN` the same way. It is a full UI session credential, not a
  scoped Private Integration Token.
- **The internal API is unofficial.** `backend.leadconnectorhq.com` has no SLA, can
  change or break without notice, and may run against GHL's ToS. The CLI prints a
  one-time warning whenever the internal path is used (suppress with
  `GHL_SUPPRESS_INTERNAL_WARNING=1`); workflows are always created as draft.
- The snippet itself only **reads** from your own browser's IndexedDB and uses the
  built-in DevTools `copy()` helper. It makes no network calls.
- Tokens refresh automatically once in `.env`; re-run the snippet only if you get an
  "expired/revoked" error.
