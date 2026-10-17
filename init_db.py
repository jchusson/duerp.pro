import os
import sys

import database

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        email, password = sys.argv[1], sys.argv[2]
    else:
        email, password = "admin@duerp.pro", "changeme"
    database.init_db()
    result = database.create_admin(email, password)
    path = database.DB_PATH
    print(f"Base initialisée : {path}")
    if result == "created":
        print(f"Compte super-admin créé : {email}")
    elif result == "updated":
        print(f"Compte super-admin mis à jour : {email} (l'ancien mot de passe par défaut a été remplacé)")
    else:
        print(f"Compte {email} existant avec un mot de passe personnalisé : aucun changement effectué.")
