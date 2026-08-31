# Project Notes

## REMINDER QUEUE (from user, not yet resolved)
- **GO-LIVE: Real SMTP is NOT configured yet.** When we go live / test the site for real,
  remind the user to collect the tuition centre's 1&1 IONOS mailbox credentials and fill
  them into `.env` (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`), then restart `runserver`.
  Until then the app stays in console-output mode (auto-fallback when those two are unset).
  - `.env` currently holds PLACEHOLDER values -> app is in SMTP mode and would fail to send
    until real credentials are entered.
  - `.env.example` documents every email key; `.env` is git-ignored (secrets never committed).

## Email config
- Django 6: legacy EMAIL_BACKEND/EMAIL_HOST/... are FORBIDDEN when `MAILERS` is set.
  All SMTP settings live inside `MAILERS['default']['OPTIONS']`:
  host, port, username, password, use_tls, timeout (lowercase).
- Auto-switch: if `EMAIL_HOST_USER` AND `EMAIL_HOST_PASSWORD` set in env -> SMTP(IONOS),
  else -> console backend. `DEFAULT_FROM_EMAIL` = the mailbox address when SMTP on.
