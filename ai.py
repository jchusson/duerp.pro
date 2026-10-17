import json
import os
import urllib.request

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")


def is_configured():
    return bool(os.environ.get("MISTRAL_API_KEY"))


def kb_recent(conn, client_id, limit=6):
    """Entrées les plus récentes de la base de connaissances du client."""
    rows = conn.execute(
        "SELECT * FROM kb_entries WHERE client_id=? ORDER BY id DESC LIMIT ?",
        (client_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        out.append({
            "hazard": r["hazard"],
            "situation": r["situation"],
            "frequency": r["frequency"],
            "severity": r["severity"],
            "mastery": r["mastery"],
            "measures": [m.strip() for m in (r["measures"] or "").split("\n") if m.strip()],
            "actions": [a.strip() for a in (r["actions"] or "").split("\n") if a.strip()],
            "source": "base de connaissances",
        })
    return out


def kb_match(conn, client_id, query, limit=6):
    """Cherche dans la base de connaissances du client les entrées dont le
    risque ou la situation contiennent la chaîne cherchée (accents/casse
    ignorés). Retourne une liste normalisée de suggestions."""
    import unicodedata
    def norm(s):
        s = unicodedata.normalize("NFD", (s or "").lower())
        return "".join(c for c in s if unicodedata.category(c) != "Mn")
    q = norm(query)
    if not q:
        return []
    rows = conn.execute(
        "SELECT * FROM kb_entries WHERE client_id=?", (client_id,)
    ).fetchall()
    out = []
    for r in rows:
        hay = norm(r["hazard"] + " " + r["situation"])
        if q in hay:
            out.append({
                "hazard": r["hazard"],
                "situation": r["situation"],
                "frequency": r["frequency"],
                "severity": r["severity"],
                "mastery": r["mastery"],
                "measures": [m.strip() for m in (r["measures"] or "").split("\n") if m.strip()],
                "actions": [a.strip() for a in (r["actions"] or "").split("\n") if a.strip()],
                "source": "base de connaissances",
            })
            if len(out) >= limit:
                break
    return out


def _chat(messages, timeout=30):
    key = os.environ["MISTRAL_API_KEY"]
    payload = json.dumps({
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        MISTRAL_API_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % key,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    return body["choices"][0]["message"]["content"]


SYSTEM_PROMPT = (
    "Tu es un expert français en prévention des risques professionnels (IPRP). "
    "Tu aides à la réalisation du Document Unique d'Évaluation des Risques Professionnels (DUERP). "
    "Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour."
)


def _post(user_prompt):
    raw = _chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        raise


def suggest_situations(work_unit_name):
    """Propose des situations dangereuses typiques pour une unité de travail."""
    prompt = (
        "Pour l'unité de travail suivante d'un établissement français : \"%s\", "
        "propose jusqu'à 6 situations dangereuses typiques, plausibles et concrètes. "
        "Pour chacune : un libellé de famille de risque court (nom de risque du DUERP, "
        "ex. 'Chute de plain-pied', 'Produits, émissions, déchets'), une description de la "
        "situation dangereuse en une phrase, la fréquence d'exposition (1 à 4 : 1 faible "
        "0-10%% du temps, 2 ponctuelle 10-40%%, 3 moyenne 40-70%%, 4 élevée 70-100%%), "
        "la gravité (1 mineure AT sans arrêt, 2 significative AT avec arrêt sans séquelles, "
        "4 critique AT avec séquelles, 8 vitale invalidité ou décès) et la maîtrise "
        "(0.5 bonne protection existante, 1 moyenne risque signalé, 2 aucune). "
        "Format JSON strict : {\"suggestions\": [{\"hazard\": \"...\", \"situation\": \"...\", "
        "\"frequency\": n, \"severity\": n, \"mastery\": n}, ...]}" % work_unit_name
    )
    return _post(prompt).get("suggestions", [])


def suggest_measures(hazard, situation):
    """Propose des mesures de prévention et des actions pour une situation dangereuse."""
    prompt = (
        "Pour le risque \"%s\" avec la situation dangereuse suivante : \"%s\", propose : "
        "1) jusqu'à 3 mesures de prévention existantes plausibles (mises en place par l'employeur) ; "
        "2) jusqu'à 3 actions de prévention à engager, chacune avec un acteur type "
        "(ex. 'Responsable technique') et une échéance envisagée (format AAAA-MM-JJ, "
        "dans les 6 à 12 mois à venir). "
        "Format JSON strict : {\"measures\": [\"...\", ...], \"actions\": "
        "[{\"text\": \"...\", \"actor\": \"...\", \"due_date\": \"AAAA-MM-JJ\"}, ...]}" % (hazard, situation)
    )
    data = _post(prompt)
    return {
        "measures": [m for m in data.get("measures", []) if isinstance(m, str) and m.strip()],
        "actions": [a for a in data.get("actions", [])
                    if isinstance(a, dict) and a.get("text", "").strip()],
    }
