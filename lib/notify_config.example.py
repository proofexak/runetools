"""
Phone alerts (lib/notify.py, PRO-93) — copy to lib/notify_config.py (gitignored) and fill in.

The webhook URL is a password: anyone who has it can post to (and delete from) the channel.
Never commit lib/notify_config.py. In the container, NOTIFY_DISCORD_WEBHOOK /
NOTIFY_DISCORD_USER_ID in docker/.env win over this file.
"""

# Discord: a private channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL.
# Empty = no alerts.
DISCORD_WEBHOOK_URL = ""

# Settings → Advanced → Developer Mode on; right-click yourself → Copy User ID. Without it the
# message has no @mention, and an unmentioned message in a muted channel won't buzz your phone.
DISCORD_USER_ID = ""

SCREENSHOT   = True   # attach the whole screen (JPEG) at the moment the bot stopped
MIN_INTERVAL = 600    # s: the same account + reason at most once per this
MAX_PER_HOUR = 10     # alerts per rolling hour, all reasons together
