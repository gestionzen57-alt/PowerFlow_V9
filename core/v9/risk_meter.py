"""RiskMeter — détecte le sentiment RISK_ON / RISK_OFF du marché Forex.

Module pur (aucune connexion DB, aucun import orchestrateur) — calcule
un sentiment institutionnel agrégé à partir des coalitions enrichies de
la Tâche A et des directions par devise du snapshot courant.

RÉFÉRENTIEL INSTITUTIONNEL
---------------------------
Groupes de devises Forex selon la doctrine institutionnelle de flux :

  * RISK_ON_DEVISES  = {AUD, NZD, CAD, GBP}  (procycliques, taux élevés)
  * RISK_OFF_DEVISES = {JPY, CHF, USD}       (refuges)
  * EUR              = neutre (peut appartenir aux deux dans une lecture
    directionnelle faible)

SENTIMENTS DÉTECTÉS
-------------------
  * RISK_ON  : coalition procyclique (AUD/NZD/CAD) haussière
               ET coalition refuge (JPY/CHF) baissière
  * RISK_OFF : coalition refuge (JPY/CHF/USD) haussière
               ET coalition procyclique (AUD/NZD/CAD) baissière
  * MIXTE    : signaux contradictoires (une coalition dans chaque sens
               mais pas l'opposition canonique)
  * NEUTRE   : pas de coalition claire détectée

INTÉGRATION
-----------
``assess(coalitions, directions, mtf_emboitement=False)`` est appelé dans
``SceneBuilder.build_scene`` après ``_detect_coalitions``. Le résultat
est stocké dans ``scenes.risk_assessment_json`` (ALTER TABLE rétrocompa-
tible géré par ``core.v9.scene_db.init_scene_db``) et injecté dans le
contexte des principes par ``principle_engine._load_shared_context``.
"""

from __future__ import annotations

from typing import Iterable

# Groupes institutionnels (constantes exportées).
RISK_ON_DEVISES: frozenset[str] = frozenset({"AUD", "NZD", "CAD", "GBP"})
RISK_OFF_DEVISES: frozenset[str] = frozenset({"JPY", "CHF", "USD"})


def _is_procyclique(devise: str) -> bool:
    return devise in RISK_ON_DEVISES


def _is_refuge(devise: str) -> bool:
    return devise in RISK_OFF_DEVISES


def _bloc_direction(
    coalitions: list[dict],
    directions: dict[str, str],
    devises_filtre: Iterable[str],
) -> tuple[str | None, float, list[str]]:
    """Détermine la direction dominante (haussiere / baissiere / None)
    d'un groupe de devises (procyclique ou refuge) à partir des
    coalitions détectées et des directions par devise.

    Renvoie un tuple ``(direction_dominante, intensite_moyenne, membres)``
    où ``membres`` est la liste aplatie des devises impliquées dans les
    coalitions retenues. Filtre uniquement les coalitions dont au moins
    la moitié des devises_alignees appartient au groupe filtre (évite de
    qualifier une coalition "AUD/JPY" comme procyclique alors qu'elle
    est mixte).
    """
    filtre = frozenset(devises_filtre)
    haussiere_intensites: list[float] = []
    baissiere_intensites: list[float] = []
    membres: list[str] = []

    for c in coalitions:
        cluster = c.get("devises_alignees") or []
        if not cluster:
            continue
        in_filter = [d for d in cluster if d in filtre]
        if len(in_filter) * 2 <= len(cluster):
            # majorité stricte (<=50%) du cluster hors du groupe : on ignore
            continue
        # Toutes les devises in_filter doivent avoir une direction
        # explicite (≠ None). Une devise sans direction = coalition
        # incomplète -> on ignore.
        directions_in_cluster = [directions.get(d) for d in in_filter]
        if any(d is None for d in directions_in_cluster):
            continue
        direction = directions_in_cluster[0]
        # Vérifie aussi que toutes les directions concordent
        if len(set(directions_in_cluster)) > 1:
            continue
        intensite = float(c.get("intensite_alignement", 0.0) or 0.0)
        if direction == "haussiere":
            haussiere_intensites.append(intensite)
            membres.extend(in_filter)
        elif direction == "baissiere":
            baissiere_intensites.append(intensite)
            membres.extend(in_filter)
        # else: direction "neutre" -> ignorée

    haussiere_mean = (
        sum(haussiere_intensites) / len(haussiere_intensites)
        if haussiere_intensites else 0.0
    )
    baissiere_mean = (
        sum(baissiere_intensites) / len(baissiere_intensites)
        if baissiere_intensites else 0.0
    )

    if haussiere_intensites and (
        not baissiere_intensites or haussiere_mean >= baissiere_mean
    ):
        return "haussiere", haussiere_mean, sorted(set(membres))
    if baissiere_intensites:
        return "baissiere", baissiere_mean, sorted(set(membres))
    return None, 0.0, []


def _score_bloc(
    blocs: list[tuple[str, float, list[str]]],
    direction_cible: str,
) -> float:
    """Score [0.0-1.0] d'un ensemble de blocs dans une direction donnée.

    Normalise l'intensité moyenne du bloc par 100 (l'intensité d'une
    coalition est une force brute centrée autour de 50, donc une
    intensité > 70 = très forte conviction).
    """
    matched = [
        (d, intensite) for d, intensite, _ in blocs if d == direction_cible
    ]
    if not matched:
        return 0.0
    mean_intensite = sum(i for _, i in matched) / len(matched)
    # Normalisation : intensité brute ∈ [0, 100], on ramène à [0, 1].
    return min(1.0, max(0.0, mean_intensite / 100.0))


def _select_dominant_coalition(
    coalitions: list[dict],
) -> dict | None:
    """Choisit la coalition dominante = celle avec la plus grande
    combinaison ``age_bars * intensite_alignement``. Sert au calcul du
    bonus ``persistance_confirmee`` et des bonus de confidence."""
    if not coalitions:
        return None
    return max(
        coalitions,
        key=lambda c: (
            int(c.get("age_bars", 1)) * float(c.get("intensite_alignement", 0.0) or 0.0)
        ),
    )


def assess(
    coalitions: list[dict],
    directions: dict[str, str],
    mtf_emboitement: bool = False,
) -> dict:
    """Évalue le sentiment RISK_ON / RISK_OFF / MIXTE / NEUTRE.

    Parameters
    ----------
    coalitions : list[dict]
        Coalitions enrichies par ``SceneBuilder._detect_coalitions`` (avec
        les 3 métriques Tâche A : age_bars, intensite_trend, stabilite).
    directions : dict[str, str]
        Directions par devise du snapshot courant (clé devise en
        majuscules, valeur ∈ {"haussiere", "baissiere", "neutre"}).
    mtf_emboitement : bool, default False
        True si la scène a détecté un emboîtement MTF (passé par
        ``SceneBuilder.build_scene`` depuis ``confluences_mtf``).

    Returns
    -------
    dict
        Voir docstring module pour la liste complète des clés.
        Toujours 8 clés, jamais d'exception sur données manquantes.
    """
    # 1) Lecture des directions dominantes par bloc institutionnel.
    proc_dir, proc_intensite, proc_membres = _bloc_direction(
        coalitions, directions, RISK_ON_DEVISES,
    )
    ref_dir, ref_intensite, ref_membres = _bloc_direction(
        coalitions, directions, RISK_OFF_DEVISES,
    )

    # 2) Scores normalisés [0.0-1.0] par direction (côté blocs).
    risk_on_score = _score_bloc(
        [(proc_dir, proc_intensite, proc_membres)],
        "haussiere",
    )
    risk_off_score = _score_bloc(
        [(ref_dir, ref_intensite, ref_membres)],
        "haussiere",
    )

    # 3) Détermination du sentiment.
    risk_sentiment = "NEUTRE"
    dominant_bloc: list[str] = []
    if (
        proc_dir == "haussiere"
        and ref_dir == "baissiere"
        and proc_intensite > 0
        and ref_intensite > 0
    ):
        risk_sentiment = "RISK_ON"
        dominant_bloc = list(set(proc_membres) | set(ref_membres))
    elif (
        ref_dir == "haussiere"
        and proc_dir == "baissiere"
        and ref_intensite > 0
        and proc_intensite > 0
    ):
        risk_sentiment = "RISK_OFF"
        dominant_bloc = list(set(proc_membres) | set(ref_membres))
    elif proc_dir is not None or ref_dir is not None:
        # Au moins un bloc s'exprime mais pas l'opposition canonique.
        # Cas MIXTE (signaux partiels / contradictoires).
        risk_sentiment = "MIXTE"
        if proc_dir is not None:
            dominant_bloc.extend(proc_membres)
        if ref_dir is not None:
            dominant_bloc.extend(ref_membres)
        dominant_bloc = sorted(set(dominant_bloc))

    # 4) Calcul de la confidence (base 40, +bonus, clamp 0-100).
    confidence = 40
    # +20 opposition nette
    if risk_sentiment in ("RISK_ON", "RISK_OFF"):
        confidence += 20
    # +15 persistance coalition dominante (age_bars >= 5)
    dominant = _select_dominant_coalition(coalitions)
    if dominant is not None:
        if int(dominant.get("age_bars", 1)) >= 5:
            confidence += 15
        # +10 stabilite >= 0.7
        if float(dominant.get("stabilite", 0.0) or 0.0) >= 0.7:
            confidence += 10
        # +10 intensite_trend montante
        if dominant.get("intensite_trend") == "montante":
            confidence += 10
    # +5 emboitement MTF
    if mtf_emboitement:
        confidence += 5
    confidence = max(0, min(100, confidence))

    # 5) Persistance confirmée : True si age_bars >= 3 sur la coalition
    # dominante ET sentiment RISK_ON/RISK_OFF (les MIXTE/NEUTRE n'ont pas
    # de coalition dominante claire).
    persistance_confirmee = (
        risk_sentiment in ("RISK_ON", "RISK_OFF")
        and dominant is not None
        and int(dominant.get("age_bars", 1)) >= 3
    )

    return {
        "risk_sentiment": risk_sentiment,
        "risk_confidence": confidence,
        "risk_on_score": round(risk_on_score, 4),
        "risk_off_score": round(risk_off_score, 4),
        "dominant_bloc": dominant_bloc,
        "refuge_bloc_direction": ref_dir or "neutre",
        "procyclique_bloc_direction": proc_dir or "neutre",
        "persistance_confirmee": persistance_confirmee,
    }