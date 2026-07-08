# Baseline APRÈS patch — 2026-07-08

État : 10 ACTIVE / 17 SHADOW (patché — PRINCIPLE_ACTIVE_IDS étendu 10→27 en Phase C1,
mais seuls les 10 principes historiques restent ACTIVE ; les 17 nouveaux
(16 GRAMMAR_* + ANTAGONIST_NODE) sont évalués en SHADOW — cf. AUDIT_R29 / ORCHESTRATION_POLICY)

Source DB : snapshot cohérent (sqlite3 backup API) de `D:/Projet/V9/data/v9_forces.db`
(prod live, non versionné) pris le 2026-07-08 — le worktree n'a pas de données live propres.
Comparer à docs/calibration/baseline_pre_20260708.md (56634/57512 évaluations, même run
de données, capturé quelques heures plus tôt — écart de ~700-900 évaluations = nouvelles
bougies accumulées entre les deux captures, pas un effet du patch).

============================================================
PowerFlow V9 - Calibration des principes (--principes)
============================================================
Principe                         Statut  Kind        Evalue  Declenche  HitRate  ConfMoy  Signaux
----------------------------------------------------------------------------------------------------
ANTAGONIST_NODE                  ACTIVE  node_rule      253          0     0.0%        -        0
COALITION_NODE                   ACTIVE  node_rule    57322         53     0.1%       73        5
ELASTIC_BREATH                   ACTIVE  node_rule    57322          5     0.0%       60        5
GRAMMAR_ABSORPTION               SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_ANTAGONISME              SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_BREAK                    SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_COALITION                SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_CONTEXTE                 SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_CROISEMENT               SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_EXHAUSTION               SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_EXTENSION                SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_GRAVITE                  SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_INVERSION                SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_LEADER_FOLLOWER          SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_LOCK                     SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_OPPOSITION               SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_PULLBACK                 SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_REGIME                   ACTIVE  grammar      58201          0     0.0%        -        0
GRAMMAR_RESPIRATION              SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_SQUEEZE                  SHADOW  grammar      58201          0     0.0%        -        0
GRAMMAR_TENSION                  SHADOW  grammar      58201          0     0.0%        -        0
GRAVITY_RESPRING_NODE            ACTIVE  node_rule    57322        256     0.4%       60      115
NODE_BIRTH_FAST                  ACTIVE  node_rule    57322        121     0.2%     68.2       48
POWER_ANGLE_BREAK_TO_PRICE_IMPACT ACTIVE  node_rule    57322        726     1.3%      100      330
PRICE_LAG_AT_NODE_BIRTH          ACTIVE  node_rule    57322      10320    18.0%     93.8     6456
RAW_NODE_BIRTH                   ACTIVE  node_rule    57322        121     0.2%       50       48
ZONE_RETEST                      ACTIVE  node_rule    57321        505     0.9%     65.4      222

------------------------------------------------------------
Suggestions (aucune modification automatique) :
  ANTAGONIST_NODE (ACTIVE) : jamais declenche (0/253) -> conditions marche non remplies ou bug integration (gap zone_diagnostics comble le 2026-07-06)

------------------------------------------------------------
Détail hit_rate par devise x TF x session (27 principes) :
------------------------------------------------------------

ANTAGONIST_NODE (253 évaluations) :
  devise : NZD=0%(n=253)
  TF     : H1=0%(n=253)
  session : asie=0%(n=217) | london=0%(n=19) | new_york=0%(n=5) | overlap=0%(n=7) | sydney=0%(n=5)

COALITION_NODE (57322 évaluations) :
  devise : NZD=0%(n=57322)
  TF     : M5=0%(n=9327) | M15=0%(n=47530) | H1=0%(n=253) | H4=0%(n=212)
  session : asie=0%(n=28668) | london=0%(n=9853) | new_york=0%(n=6394) | overlap=0%(n=8223) | sydney=0%(n=4184)

ELASTIC_BREATH (57322 évaluations) :
  devise : NZD=0%(n=57322)
  TF     : M5=0%(n=9327) | M15=0%(n=47530) | H1=0%(n=253) | H4=0%(n=212)
  session : asie=0%(n=28668) | london=0%(n=9853) | new_york=0%(n=6394) | overlap=0%(n=8223) | sydney=0%(n=4184)

GRAMMAR_ABSORPTION (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_ANTAGONISME (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_BREAK (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_COALITION (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_CONTEXTE (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_CROISEMENT (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_EXHAUSTION (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_EXTENSION (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_GRAVITE (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_INVERSION (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_LEADER_FOLLOWER (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_LOCK (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_OPPOSITION (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_PULLBACK (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_REGIME (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_RESPIRATION (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_SQUEEZE (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAMMAR_TENSION (58201 évaluations) :
  devise : NZD=0%(n=58201)
  TF     : M1=0%(n=373) | M5=0%(n=9327) | M15=0%(n=47530) | M30=0%(n=304) | H1=0%(n=253) | H4=0%(n=212) | D1=0%(n=202)
  session : asie=0%(n=29272) | london=0%(n=10011) | new_york=0%(n=6404) | overlap=0%(n=8236) | sydney=0%(n=4278)

GRAVITY_RESPRING_NODE (57322 évaluations) :
  devise : NZD=0%(n=57322)
  TF     : M5=1%(n=9327) | M15=0%(n=47530) | H1=1%(n=253) | H4=0%(n=212)
  session : asie=0%(n=28668) | london=0%(n=9853) | new_york=0%(n=6394) | overlap=0%(n=8223) | sydney=1%(n=4184)

NODE_BIRTH_FAST (57322 évaluations) :
  devise : NZD=0%(n=57322)
  TF     : M5=0%(n=9327) | M15=0%(n=47530) | H1=0%(n=253) | H4=0%(n=212)
  session : asie=0%(n=28668) | london=0%(n=9853) | new_york=0%(n=6394) | overlap=0%(n=8223) | sydney=0%(n=4184)

POWER_ANGLE_BREAK_TO_PRICE_IMPACT (57322 évaluations) :
  devise : NZD=1%(n=57322)
  TF     : M5=3%(n=9327) | M15=1%(n=47530) | H1=3%(n=253) | H4=0%(n=212)
  session : asie=1%(n=28668) | london=1%(n=9853) | new_york=1%(n=6394) | overlap=1%(n=8223) | sydney=3%(n=4184)

PRICE_LAG_AT_NODE_BIRTH (57322 évaluations) :
  devise : NZD=18%(n=57322)
  TF     : M5=7%(n=9327) | M15=20%(n=47530) | H1=7%(n=253) | H4=1%(n=212)
  session : asie=33%(n=28668) | london=3%(n=9853) | new_york=2%(n=6394) | overlap=2%(n=8223) | sydney=6%(n=4184)

RAW_NODE_BIRTH (57322 évaluations) :
  devise : NZD=0%(n=57322)
  TF     : M5=0%(n=9327) | M15=0%(n=47530) | H1=0%(n=253) | H4=0%(n=212)
  session : asie=0%(n=28668) | london=0%(n=9853) | new_york=0%(n=6394) | overlap=0%(n=8223) | sydney=0%(n=4184)

ZONE_RETEST (57321 évaluations) :
  devise : NZD=1%(n=57321)
  TF     : M5=2%(n=9326) | M15=1%(n=47530) | H1=4%(n=253) | H4=1%(n=212)
  session : asie=1%(n=28667) | london=1%(n=9853) | new_york=1%(n=6394) | overlap=1%(n=8223) | sydney=2%(n=4184)
