---
name: powerflow-v9-test-scaffold
category: software-development
description: Scaffolding automatique de tests pour couches V9 (SceneBuilder, BehaviorAnalyzer, PrincipleEngine, RiskMeter). Génère la fixture init_db/init_scene_db + helpers d'insertion + cas limites à partir d'une fonction cible.
trigger: '"Nouveau module V9 à tester" | "Régression couverte par quel test" | "Scaffolder tests pour X"'
tools_needed: [terminal, read_file, write_file, execute_code]
---

## 🎯 OBJECTIF

Réduire de ~80% le coût d'écriture des tests pour les 4 couches cognitives V9
(Scènes, Comportements, Principes, Risk) en générant le squelette
`init_db(tmp_path) → helpers d'insertion → fixtures JSON → assert` à partir de
la signature de la fonction à tester.

Contexte observé (session 2026-07-06, Tâche A+B+C) : 21 tests écrits à la main
en 1 session, pattern `init_db / _insert_row / builder / assert` répété
systématiquement, 0% de variabilité structurelle entre tests du même module.

## 🔍 DIAGNOSTIC RAPIDE

```bash
# 1. Identifier la couche cible + fonction
grep -rn "def _detect_coalitions\|def _compute_confiance\|def assess" core/v9/

# 2. Vérifier le helper existant (_make_builder, _insert_row, _default_row)
grep -n "_make_builder\|_insert_row\|_default_row" tests/test_scene_builder.py | head -5

# 3. Voir les fixtures de référence
ls tests/fixtures/
```

## 🛠️ SCAFFOLDER — `scripts/scaffold_v9_tests.py`

### Étape 1 — Inventaire des tests existants du module cible

```python
# scripts/scaffold_v9_tests.py
from pathlib import Path
import re

def inventory_existing_tests(module_name: str) -> dict:
    """Parse tests/test_<module>.py et retourne les fonctions de test,
    helpers, fixtures utilisés. Sert à calibrer le scaffold."""
    test_path = Path(f"tests/test_{module_name}.py")
    if not test_path.exists():
        return {"tests": [], "helpers": [], "fixtures": []}
    content = test_path.read_text(encoding="utf-8")
    tests = re.findall(r"^def (test_\w+)\(", content, re.MULTILINE)
    helpers = re.findall(r"^def (_helper_\w+|_make_\w+|_insert_\w+|_default_\w+)\(", content, re.MULTILINE)
    fixtures_used = re.findall(r"FIXTURE_PATH\s*=\s*Path\(__file__\)\.parent\s*/\s*['\"]fixtures/(\w+)['\"]", content)
    return {"tests": tests, "helpers": helpers, "fixtures": fixtures_used}
```

### Étape 2 — Générer le squelette pour une fonction cible

```python
# Signature analysée : f(a: int, b: str = "x") -> dict
# Cas limites automatiques : a=0, a=-1, a=max, b=None, b=""

def scaffold_test_for(target_module: str, function_name: str,
                      edge_cases: list[dict] = None) -> str:
    """Génère un test pytest suivant le pattern V9 (init_db + helpers +
    assert). Retourne le code Python prêt à coller dans test_<module>.py."""
    template = '''
def test_{func}_edge_case_{idx}(tmp_path):
    """Cas limite : {description}"""
    {fixture_init}
    builder = _make_builder(tmp_path)
    # TODO: appel de {func} avec inputs edge_case
    result = builder.{func}({args})
    # TODO: assert attendu
    assert result is not None
'''
    if edge_cases is None:
        edge_cases = [{"args": "{}", "description": "default"}]
    return "\n".join([
        template.format(func=function_name, idx=i, args=ec["args"],
                       description=ec["description"], fixture_init=_fixture_init_for(target_module))
        for i, ec in enumerate(edge_cases)
    ])

def _fixture_init_for(module_name: str) -> str:
    """Retourne le bloc d'init DB + helpers selon le module."""
    return {
        "scene_builder": "from core.v9.scene_builder import SceneBuilder\n    init_db(tmp_path / 'test.db')\n    init_scene_db(tmp_path / 'test.db')",
        "behavior_analyzer": "from core.v9.behavior_analyzer import BehaviorAnalyzer\n    init_db(db_path); init_scene_db(db_path); init_behavior_db(db_path)",
        "principle_engine": "from core.v9.principle_engine import PrincipleEngine\n    init_db(db_path); init_scene_db(db_path); init_behavior_db(db_path)",
        "risk_meter": "from core.v9.risk_meter import assess",
    }.get(module_name, "")
```

### Étape 3 — Cas limites typiques par couche

```python
EDGE_CASES_BY_LAYER = {
    "scene_builder": [
        {"args": "{}", "description": "no forces, no history"},
        {"args": "{'USD': 100.0}", "description": "single force spike"},
        {"args": "{'USD': 50.0, 'JPY': 50.0}", "description": "neutral baseline"},
        {"args": "{'USD': 90.0, 'EUR': 10.0}", "description": "extreme divergence"},
    ],
    "risk_meter": [
        {"args": "[]", "description": "empty coalitions"},
        {"args": "coalitions_with_no_dominance", "description": "all neutral"},
        {"args": "procyclique_up_refuge_down", "description": "RISK_ON canonique"},
        {"args": "refuge_up_procyclique_down", "description": "RISK_OFF canonique"},
    ],
    "principle_engine": [
        {"args": "snapshot_without_scene", "description": "fallback sans scene"},
        {"args": "scene_with_all_fields", "description": "contexte complet"},
        {"args": "scene_with_invalid_json", "description": "JSON corrompu -> fallback"},
    ],
}
```

## ⚠️ Pièges identifiés (sessions 2026-07-06, S2-S3)

### Bug silencieux « signaux directionnels sans décision » (S2 commit d2f6c60)
- **Symptôme** : `signals` contient `direction != None` mais `decisions.direction IS NOT NULL` reste à 0.
- **Cause** : `DecisionLogger._load_signal()` faisait `ORDER BY id DESC LIMIT 1`. Un signal non-directionnel créé tôt pour le snapshot était élu au lieu du signal directionnel ultérieur.
- **Fix** : `ORDER BY (directionnel AND exploitable) DESC, id DESC` — pertinence décisionnelle d'abord.
- **Test de régression** : `test_load_signal_prefers_directional_exploitable_on_same_snapshot` (test_decision_logger.py) — bascule UPDATE 1er signal en non-directionnel, INSERT 2ème directionnel, vérifie que .log() produit une décision directionnelle.

### Idempotence decisions (S3 commit 3d42b6c)
- **Symptôme** : `decision_id = timestamp+uuid` changeait à chaque `.log()` → `INSERT OR REPLACE` créait une nouvelle rangée (3697 → 3960 sur 3 rejoues).
- **Fix** : `decision_id = uuid5(snapshot_id).hex[:12]` (déterministe) + pré-check `_action_quality()` (preparer_entree=3 > surveiller=2 > observer=1 > aucune_action=0).
- **3 tests de régression** : `test_decision_idempotent_same_snapshot_no_duplicate` (3 log() → 1 rangée même decision_id), `test_decision_replaces_nondirectional_with_directional` (cas emblématique session 2), `test_decision_keeps_best_on_multiple_replay` (qualité skip).

### Gardien permanent (S3 commit 85b40fe)
`tests/test_pipeline_end_to_end.py` détecte régression sur les 5 bugs silencieux S2. Pattern canonique :
- DB SQLite tmp + `ignore_cleanup_errors=True` Windows WAL
- `row_factory = sqlite3.Row` **obligatoire** sur les connexions
- `from core.v9.db_schema import get_connection` + tous les init_db() requis dans la fixture
- Couche SceneBuilder.build_scene() traversée en réel, behavior/window/exploitability injectés (heuristique single-snapshot instable), zone/regime/principe multi-snapshot injectés
- Timestamps figés (ex. `2026-07-05T17:00:00.000Z`) → reproductibilité totale

---

## ✅ VALIDATION

```bash
# 1. Le scaffold doit produire du code qui parse
python -c "import ast; ast.parse(open('tests/test_scene_builder.py').read())"

# 2. Pattern de tests V9 respecté : helpers _make_*, _insert_*, init_db/init_scene_db
grep -E "^def (_make_|_insert_|_default_)" tests/test_<module>.py

# 3. Couverture ≥80% sur la fonction cible
python -m pytest tests/test_<module>.py --cov=core.v9.<module> --cov-report=term-missing
```

## 📚 RÉFÉRENCES

- Pattern observé : `tests/test_scene_builder.py` (26 tests), `tests/test_risk_meter.py` (20 tests)
- Helpers existants : `_make_builder`, `_insert_row`, `_default_row` (scene_builder), `_setup`, `_add_scene`, `_insert_forces_snapshot` (behavior_analyzer), `_insert_full_chain` (principle_engine)
- Format : frontmatter YAML + sections 🎯/🔍/🛠️/✅ (cohérent avec powerflow-patch-p0, powerflow-recit-causal)