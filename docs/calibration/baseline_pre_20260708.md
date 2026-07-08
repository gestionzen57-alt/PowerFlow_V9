# Baseline AVANT patch — 2026-07-08
État : 10 ACTIVE / 17 SHADOW (non patché)
Référence pour Phase D post-C

============================================================
PowerFlow V9 - Calibration des principes (--principes)
============================================================
Principe                         Statut  Kind        Evalue  Declenche  HitRate  ConfMoy  Signaux
----------------------------------------------------------------------------------------------------
ANTAGONIST_NODE                  ACTIVE  node_rule      253          0     0.0%        -        0
COALITION_NODE                   ACTIVE  node_rule    56634         53     0.1%       73        5
ELASTIC_BREATH                   ACTIVE  node_rule    56634          5     0.0%       60        5
GRAMMAR_ABSORPTION               SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_ANTAGONISME              SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_BREAK                    SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_COALITION                SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_CONTEXTE                 SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_CROISEMENT               SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_EXHAUSTION               SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_EXTENSION                SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_GRAVITE                  SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_INVERSION                SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_LEADER_FOLLOWER          SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_LOCK                     SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_OPPOSITION               SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_PULLBACK                 SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_REGIME                   ACTIVE  grammar      57512          0     0.0%        -        0
GRAMMAR_RESPIRATION              SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_SQUEEZE                  SHADOW  grammar      57512          0     0.0%        -        0
GRAMMAR_TENSION                  SHADOW  grammar      57512          0     0.0%        -        0
GRAVITY_RESPRING_NODE            ACTIVE  node_rule    56634        253     0.4%       60      112
NODE_BIRTH_FAST                  ACTIVE  node_rule    56634        121     0.2%     68.2       48
POWER_ANGLE_BREAK_TO_PRICE_IMPACT ACTIVE  node_rule    56634        717     1.3%      100      321
PRICE_LAG_AT_NODE_BIRTH          ACTIVE  node_rule    56634      10302    18.2%     93.8     6438
RAW_NODE_BIRTH                   ACTIVE  node_rule    56634        121     0.2%       50       48
ZONE_RETEST                      ACTIVE  node_rule    56633        499     0.9%     65.4      216

------------------------------------------------------------
Suggestions (aucune modification automatique) :
  ANTAGONIST_NODE (ACTIVE) : jamais declenche (0/253) -> conditions marche non remplies ou bug integration (gap zone_diagnostics comble le 2026-07-06)
