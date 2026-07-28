"""Shared issue #126 replay data from shadow-parity record DRIFT-021."""

DRIFT_021_ASSERTION = (
    "**Don't customize the installed YAML beyond the cron/cap/bloat-cron/"
    "upgrade-cron knobs.** Real changes belong upstream in the plugin "
    "(aj604/toolshed) so every install gets them on next upgrade."
)

DRIFT_021_PREIMAGE = (
    "- **Don't customize the installed YAML beyond the cron/cap/bloat-cron/"
    "upgrade-cron knobs.** Real\n"
    "  changes belong upstream in the plugin (aj604/toolshed) so every install "
    "gets them on next upgrade."
)

DRIFT_021_FIX = (
    "- **Don't customize the installed YAML beyond the cron/cap/bloat-cron/"
    "upgrade-cron/audit-cron\n"
    "  knobs.** Real changes belong upstream in the plugin (aj604/toolshed) so "
    "every install gets them on\n"
    "  next upgrade."
)
