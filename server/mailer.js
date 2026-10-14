// Sends the one-time sign-in code for email 2FA. Three backends, auto-detected:
//   - RESEND_API_KEY  -> Resend HTTP API (zero extra deps; easiest to stand up)
//   - SMTP_URL or SMTP_HOST -> any SMTP mailbox via nodemailer (e.g. Google Workspace)
//   - TWOFA_DEV_ECHO=1 -> logs the code to the server console (LOCAL TESTING ONLY)
// MAIL_FROM sets the From header (default noreply@growth-factor.ai).

let _transport;
async function smtpTransport() {
  if (_transport) return _transport;
  const { default: nodemailer } = await import('nodemailer');
  _transport = process.env.SMTP_URL
    ? nodemailer.createTransport(process.env.SMTP_URL)
    : nodemailer.createTransport({
        host: process.env.SMTP_HOST,
        port: Number(process.env.SMTP_PORT || 587),
        secure: process.env.SMTP_SECURE === '1',
        auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS } : undefined,
      });
  return _transport;
}

// True when at least one backend (incl. the dev echo) is available to deliver a code.
export function mailerConfigured() {
  return !!(process.env.TWOFA_DEV_ECHO === '1' || process.env.RESEND_API_KEY || process.env.SMTP_URL || process.env.SMTP_HOST);
}

export async function sendCode(to, code) {
  const from = process.env.MAIL_FROM || 'Growth Factor <noreply@growth-factor.ai>';
  const subject = 'Your Growth Factor sign-in code';
  const text = `Your Growth Factor sign-in code is ${code}\n\nIt expires in 10 minutes. If you didn't just try to sign in, ignore this email and change your password.`;

  // Dev echo wins so local testing never actually emails anyone.
  if (process.env.TWOFA_DEV_ECHO === '1') { console.log(`[2fa] DEV sign-in code for ${to}: ${code}`); return { dev: true }; }

  if (process.env.RESEND_API_KEY) {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ from, to, subject, text }),
    });
    if (!r.ok) throw new Error(`resend_${r.status}: ${(await r.text()).slice(0, 200)}`);
    return { ok: true };
  }

  if (process.env.SMTP_URL || process.env.SMTP_HOST) {
    const t = await smtpTransport();
    await t.sendMail({ from, to, subject, text });
    return { ok: true };
  }

  throw new Error('mailer_not_configured');
}
