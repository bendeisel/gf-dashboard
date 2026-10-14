#!/usr/bin/env node
// Generate a scrypt password hash for DASHBOARD_USERS, so real passwords never sit in
// plaintext in .env. Usage:
//   node server/hash-password.js 'the password'
//   node server/hash-password.js            (prompts, no echo)
// Paste the printed `scrypt$...` value as the user's password in DASHBOARD_USERS, e.g.
//   DASHBOARD_USERS="ben:scrypt$...,lorenz:scrypt$..."
import crypto from 'node:crypto';
import readline from 'node:readline';

export function hashPassword(plain) {
  const salt = crypto.randomBytes(16);
  const hash = crypto.scryptSync(plain, salt, 32);
  return `scrypt$${salt.toString('base64')}$${hash.toString('base64')}`;
}

async function prompt() {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
  // best-effort no-echo
  const out = process.stdout;
  rl._writeToOutput = () => out.write('*');
  return new Promise((res) => rl.question('Password: ', (a) => { rl.close(); out.write('\n'); res(a); }));
}

// run directly (not when imported)
if (import.meta.url === `file://${process.argv[1]}`) {
  const arg = process.argv.slice(2).join(' ');
  const run = async () => {
    const pw = arg || (await prompt());
    if (!pw) { console.error('No password given.'); process.exit(1); }
    console.log(hashPassword(pw));
  };
  run();
}
