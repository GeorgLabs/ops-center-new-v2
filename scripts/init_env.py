"""Creates .env with fresh random secrets (only if it does not exist yet).

    python scripts/init_env.py

The admin password is printed ONCE, here. It is also in .env - keep that file private.
"""

import secrets
from pathlib import Path

env = Path(__file__).resolve().parent.parent / ".env"
if env.exists():
    print(".env exists - leaving it alone.")
else:
    admin_password = secrets.token_urlsafe(18)
    env.write_text(
        "# Ops Center settings. Never share or commit this file.\n"
        f"OPS_SECRET_KEY={secrets.token_urlsafe(48)}\n"
        "# 1 = development (API docs on /docs, Mission Control, Traffic). Use 0 for anything real.\n"
        "OPS_DEV=1\n"
        "# The first administrator is created at startup if no user with this name exists yet.\n"
        "# Changing the password here later has no effect - use 'Account > Change password' in the app.\n"
        "OPS_ADMIN_USERNAME=admin\n"
        f"OPS_ADMIN_PASSWORD={admin_password}\n"
        "# true = anyone can register, false = only admins create accounts\n"
        "OPS_ALLOW_REGISTRATION=true\n",
        encoding="utf-8",
    )
    print("Created .env with new random secrets. Never share or commit this file.")
    print(f"Admin login:  admin / {admin_password}   (also stored in .env)")
