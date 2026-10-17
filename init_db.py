import os
import sys

import database

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        email, password = sys.argv[1], sys.argv[2]
    else:
        email, password = "admin@duerp.pro", "changeme"
    database.init_db()
    database.create_admin(email, password)
    path = database.DB_PATH
    print(f"Base initialisée : {path}")
    print(f"Compte super-admin : {email} (mot de passe fourni à changer immédiatement)")
