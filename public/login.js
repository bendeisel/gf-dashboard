// Two-step sign-in: password, then (when 2FA is active) an emailed one-time code.
const $ = (id) => document.getElementById(id);
const step1 = $('step1'), step2 = $('step2');

async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}
function showStep2(email) {
  $('maskedEmail').textContent = email || 'your email';
  step1.hidden = true; step2.hidden = false;
  $('code').value = ''; $('code').focus();
}
function showStep1(msg) {
  step2.hidden = true; step1.hidden = false;
  $('err1').textContent = msg || '';
  $('pw').value = ''; $('pw').focus();
}

step1.addEventListener('submit', async (e) => {
  e.preventDefault();
  $('err1').textContent = '';
  const { ok, data } = await post('/api/login', { username: $('user').value, password: $('pw').value });
  if (ok && data.twofa) return showStep2(data.email);
  if (ok) return void (location.href = '/');
  $('err1').textContent = data.error || 'Sign in failed.';
});

step2.addEventListener('submit', async (e) => {
  e.preventDefault();
  $('err2').textContent = '';
  const { ok, status, data } = await post('/api/login/verify', { code: $('code').value });
  if (ok) return void (location.href = '/');
  if (status === 440) return showStep1(data.error); // challenge expired → back to step 1
  $('err2').textContent = data.error || 'Verification failed.';
});

$('resend').addEventListener('click', async (e) => {
  e.preventDefault();
  $('err2').textContent = '';
  const { ok, data } = await post('/api/login/resend', {});
  $('err2').textContent = ok ? 'A new code is on its way.' : (data.error || 'Could not resend.');
});
$('back').addEventListener('click', (e) => { e.preventDefault(); showStep1(''); });
