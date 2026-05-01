"""Generate a bcrypt password hash for ADMIN_PASSWORD_HASH env var.

Usage:
    python -m app.debug_scripts.generate_password_hash
"""

import sys
from getpass import getpass

from app.core.security import hash_password


def main() -> None:
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass("Enter password: ")
        confirm = getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match")
            sys.exit(1)

    print(f"\nADMIN_PASSWORD_HASH={hash_password(password)}")


if __name__ == "__main__":
    main()
