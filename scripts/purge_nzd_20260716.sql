-- ============================================================================
-- purge_nzd_20260716.sql — Neutralisation du biais NZD dans principle_evaluations
-- ============================================================================
-- Contexte (audit OUVERTURE DES YEUX 2026-07-16) :
--   principle_evaluations = 657 284 lignes, dont 655 724 currency='NZD'
--   (99,76 %). Or 100 % des snapshots sous-jacents sont GBPUSD. Le label
--   currency=NZD est un ARTEFACT PRÉ-FIX : avant le 14/07 le vote-devise
--   assignait tout à NZD (100 % NZD jusqu'au 14/07). Le fix « vote NZD »
--   du 15/07 fait apparaître les autres devises mais NZD reste ~97 % du
--   flux quotidien : le fix n'a que PARTIELLEMENT résolu le vote-devise
--   (gap résiduel séparé, à traiter dans la logique d'évaluation — hors
--   périmètre de ce script).
--
--   Les `decisions` (67 811 GBPUSD) ne sont PAS concernées : elles sont
--   propres (symbole réel) et ont servi au paper-trade. NE PAS y toucher.
--
-- DÉCISION À PRENDRE PAR SØN : Option A (vue, non-destructive) ou
-- Option B (purge destructive). Ce script exécute UNIQUEMENT l'option A.
-- L'option B reste commentée : décision humaine explicite requise.
-- ============================================================================

-- Décompte de contrôle (lecture seule) --------------------------------------
--   SELECT currency, COUNT(*) FROM principle_evaluations GROUP BY currency;

-- ============================================================================
-- OPTION A (RECOMMANDÉE, NON-DESTRUCTIVE) — vue filtrée
-- ----------------------------------------------------------------------------
-- Ne touche PAS aux données brutes. Exclut NZD pour tout backtest / calibration
-- cross-devise. Réversible instantanément : DROP VIEW v_principle_evaluations_clean;
-- ============================================================================
DROP VIEW IF EXISTS v_principle_evaluations_clean;
CREATE VIEW v_principle_evaluations_clean AS
SELECT *
FROM principle_evaluations
WHERE currency != 'NZD';

-- Vérification post-création (lecture seule) :
--   SELECT COUNT(*) FROM v_principle_evaluations_clean;   -- ~1 560 lignes

-- ============================================================================
-- OPTION B (DESTRUCTIVE) — NE PAS EXÉCUTER SANS VALIDATION SØN + BACKUP
-- ----------------------------------------------------------------------------
-- PRÉREQUIS OBLIGATOIRES avant toute exécution :
--   1. Arrêter la capture (python -m core.v9.capture_server est LIVE).
--   2. Backup : cp data/v9_forces.db data/v9_forces.db.bak_20260716
--   3. MD5 du backup consigné dans DECISIONS_LOG.
-- Gain : ~655 724 lignes supprimées (allègement DB significatif, ~1 GB+).
-- Irréversible. Ne supprime QUE principle_evaluations (jamais decisions).
-- ----------------------------------------------------------------------------
--   DELETE FROM principle_evaluations WHERE currency = 'NZD';
--   VACUUM;   -- récupère l'espace disque (nécessite ~2x la taille libre)
-- ============================================================================
