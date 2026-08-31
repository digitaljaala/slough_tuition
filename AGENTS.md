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

## Roadmap (refined into small, independently-verifiable sub-modules)
Each line = one commit-ready unit of work. Mark [x] when done.
### Session booking
- [x] 1. Bookable list UI — staff sees every student + payment plan + sessions remaining (`/staff/bookings/`, `staff/booking_hub.html`).
- [x] 2. Centre 8-block consumption — booking a centre session increments `Student.sessions_used_in_block`, reducing `remaining_sessions`; home = per-session/unlimited.
- [x] 3. Home per-session billing — booking a home session creates a per-session invoice line (`Invoice.for_home_session`), incl. one-off assessment fee on first invoice.
- [ ] 4. Custom/override deals — booking against a manually-priced plan / custom_price.
- [ ] 5. Block renewal / reset — when a block is fully consumed, prompt to charge a new block and reset `sessions_used_in_block`.
### Assessment + PDF
- [x] 6. Assessment polish — edit/update, save history view.
- [x] 7. Mobile-friendly PDF report (weasyprint or reportlab).
- [x] 8. Email PDF to parent (attachment).
### Billing (superuser only)
- [ ] 9. Invoices list — filter by plan/status, outstanding balances.
- [ ] 10. Invoice generation from consumed sessions.
- [ ] 11. Payment recording — mark paid/partial, plan create/override.
- [ ] 12. Reports / export — CSV + summary.
### Parent portal
- [ ] 13. Parent sees own invoice / assessment history.
### Parent account & password recovery (separate, user-requested)
- [x] 14. Self-service forgot-password flow (reset email + set new password), link on login page; parent addressed by name.
- [x] 15. Duplicate-safe reset — only fires when email maps to exactly one account+parent row, else logged for centre (never a wrong-person reset or new record).
- [x] 16. Block re-registration with a used email + guide to login/reset; `register_student` dedupes parent rows by email (reuses, never duplicates).
- [x] 17. `reconcile_parents` command to merge existing duplicates + link orphan parents (`--commit`, `--verbose`; applied to live DB).
- [x] 18. Staff tool (superuser-only) to find a parent by name/email and reset their password / create a login if none.
- [x] 19. Parent self-service `edit_parent` keeps contact email and login email in sync (User.email == Parent.email), and rejects emails already used as another account's login.
- [x] 20. Email/login desync bug fixed: changing parent email now updates the login User too (was the last open loose end in this section).

## Work state
- Module 1 (billing foundation): DONE & pushed.
- Module 2 (staff console: sessions/assessments/students): DONE, browser-verified, pushed.
- Sub-modules 1-3 (bookable list UI + centre block consumption + home per-session billing): DONE (38 tests), browser-verified.
- Parent account & password recovery (sub-modules 14-20) + email/login sync fix: DONE (61 tests), browser-verified, pushed.
- Assessment + PDF (sub-modules 6-8): DONE (edit/delete history, reportlab PDF, email attach), 66 tests passing, pushed. NOTE: assessment `percentage` set only via `AssessmentForm.clean()`; direct `Assessment.objects.create()` leaves it NULL.
- 66 tests passing. Tailwind compiled after template changes.
- .env holds PLACEHOLDER email creds (console fallback mode until real IONOS creds filled in).
- DB: Postgres `slough_tuition` @ localhost; superuser admin@example.com / AdminPass123! (password reset for QA; change if needed); staff staff@example.com / StaffPass123!.
